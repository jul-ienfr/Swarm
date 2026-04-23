from __future__ import annotations

import inspect
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
import yaml
from typer.models import OptionInfo
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

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
from runtime_contracts.intent import EnginePreference, TaskType
from runtime_langgraph import build_initial_state, build_resume_config, build_status_config, compile_graph
from swarm_core.deliberation import DeliberationResult, load_deliberation_result, replay_deliberation_sync
import swarm_core.deliberation_campaign as deliberation_campaign_core
from swarm_core.deliberation_interview import (
    DeliberationInterviewResponse,
    interview_deliberation_sync,
    list_deliberation_targets,
)
from swarm_core.deliberation_campaign import (
    DeliberationCampaignBenchmarkBundle,
    DeliberationCampaignMatrixBenchmarkBundle,
    DeliberationCampaignMatrixBenchmarkComparisonAudit,
    DeliberationCampaignMatrixBenchmarkComparisonExport,
    DeliberationCampaignMatrixBenchmarkComparisonReport,
    DeliberationCampaignMatrixCandidateSpec,
    DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR as CORE_DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR,
    DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR as CORE_DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR,
    DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR as CORE_DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR,
    DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR as CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR,
    DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR as CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR,
    DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR as CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR,
    DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR as CORE_DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR,
    build_deliberation_campaign_comparison_export,
    DeliberationCampaignComparisonAudit,
    DeliberationCampaignComparisonExport,
    DeliberationCampaignComparisonReport,
    DeliberationCampaignReport,
    DeliberationCampaignStatus,
    load_deliberation_campaign_benchmark,
    load_deliberation_campaign_matrix_benchmark_comparison_report,
    load_deliberation_campaign_matrix_benchmark,
    load_deliberation_campaign_report,
    list_deliberation_campaign_benchmarks,
    list_deliberation_campaign_matrix_benchmark_comparison_reports,
    list_deliberation_campaign_matrix_benchmarks,
    run_deliberation_campaign_sync,
    run_deliberation_campaign_matrix_benchmark_sync,
)
from swarm_core.deliberation_persona_chat import DeliberationPersonaChatService
from swarm_core.deliberation_artifacts import DeliberationMode
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
    runtime_health,
)
from swarm_core import (
    DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH,
    DEFAULT_BENCHMARK_SUITE_PATH,
    DEFAULT_HARNESS_MEMORY_PATH,
    DEFAULT_HARNESS_RUN_MAPPING_PATH,
    OptimizationMode,
    inspect_harness,
    run_harness_optimization,
)
from swarm_core.benchmark_suite import BenchmarkProfile

app = typer.Typer(help="Swarm Multi-Agent Research Harness")
harness_app = typer.Typer(help="Harness self-improvement, inspection, and suggest-only optimization.")
improve_app = typer.Typer(help="Generic improvement-loop targets, rounds, and bounded loops.")
prediction_markets_app = typer.Typer(help="Prediction markets advisor, replay, and paper-trading MVP.")
app.add_typer(harness_app, name="harness")
app.add_typer(improve_app, name="improve")
app.add_typer(prediction_markets_app, name="prediction-markets")
app.add_typer(prediction_markets_app, name="polymarket")
console = Console()
DEFAULT_OPENCLAW_CONFIG_PATH = Path("/home/jul/.openclaw/openclaw.json")
DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR = CORE_DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR
DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR = CORE_DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR
DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR = (
    CORE_DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR
)
DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR = CORE_DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR
DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR = (
    CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR
)
DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR = (
    CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR
)
DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR = (
    Path(__file__).resolve().parent / "data" / "deliberation_campaign_matrix_benchmark_exports"
)
DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR = (
    Path(__file__).resolve().parent / "data" / "deliberation_campaign_matrix_benchmark_export_comparisons"
)
DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR = (
    Path(__file__).resolve().parent / "data" / "deliberation_campaign_matrix_benchmark_export_comparison_exports"
)
DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR = CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR


def _print_json(payload: Any) -> None:
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def _shorten_text(value: Any, *, max_length: int = 72) -> str:
    text = " ".join(str(value).split())
    if len(text) <= max_length:
        return text
    return text[: max(0, max_length - 3)].rstrip() + "..."


def _format_kv_line(*pairs: tuple[str, Any]) -> str:
    tokens: list[str] = []
    for label, value in pairs:
        if value is None:
            continue
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                continue
            tokens.append(f"{label}={normalized}")
        elif isinstance(value, bool):
            tokens.append(f"{label}={'yes' if value else 'no'}")
        else:
            tokens.append(f"{label}={value}")
    return " | ".join(tokens) if tokens else "n/a"


def _first_text_value(*values: Any) -> str | None:
    for value in values:
        if value is None or isinstance(value, (dict, list, tuple, set)):
            continue
        text = " ".join(str(value).split())
        if text:
            return text
    return None


def _comparability_identity_tokens(result: Any, comparability: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    metadata = result.metadata if isinstance(getattr(result, "metadata", None), dict) else {}
    return (
        (
            "run",
            _first_text_value(
                comparability.get("run_id"),
                comparability.get("meeting_id"),
                comparability.get("deliberation_id"),
                metadata.get("run_id"),
                metadata.get("meeting_id"),
                metadata.get("deliberation_id"),
                getattr(result, "meeting_id", None),
                getattr(result, "deliberation_id", None),
            ),
        ),
        (
            "config",
            _first_text_value(
                comparability.get("input_fingerprint"),
                comparability.get("input_hash"),
                comparability.get("workbench_input_hash"),
                comparability.get("topic_fingerprint"),
                comparability.get("objective_fingerprint"),
                comparability.get("participant_fingerprint"),
                comparability.get("config_id"),
                comparability.get("config_path"),
                metadata.get("config_id"),
                metadata.get("config_path"),
            ),
        ),
        (
            "runtime_id",
            _first_text_value(
                comparability.get("execution_fingerprint"),
                comparability.get("model_name"),
                comparability.get("provider_base_url"),
                comparability.get("runtime_fingerprint"),
                comparability.get("runtime_id"),
                metadata.get("runtime_id"),
                metadata.get("model_name"),
                metadata.get("provider_base_url"),
                getattr(result, "runtime_id", None),
            ),
        ),
    )


def _summarize_warning_codes(warnings: Any, *, max_items: int = 3) -> str:
    if warnings is None:
        return "none"
    if not isinstance(warnings, list):
        return "n/a"
    normalized = [str(item).strip() for item in warnings if str(item).strip()]
    if not normalized:
        return "none"
    head = ", ".join(normalized[:max_items])
    if len(normalized) > max_items:
        head += f" (+{len(normalized) - max_items} more)"
    return f"{len(normalized)} ({head})"


def _deliberation_stability_line(result: DeliberationResult) -> str | None:
    stability = result.stability_summary
    if stability is None:
        return None
    metric_name = getattr(stability, "metric_name", None) or stability.metadata.get("metric_name", "overall")
    comparison_key = getattr(stability, "comparison_key", None) or stability.metadata.get("comparison_key")
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    return _format_kv_line(
        ("runs", stability.sample_count),
        ("stable", stability.stable),
        ("guard", metadata.get("stability_guard_applied")),
        ("metric", metric_name),
        ("spread", f"{stability.score_spread:.3f}"),
        ("key", _shorten_text(comparison_key, max_length=40) if comparison_key else None),
    )


def _deliberation_comparability_line(result: DeliberationResult) -> str:
    comparability = result.metadata.get("comparability", {}) if isinstance(result.metadata, dict) else {}
    if not isinstance(comparability, dict):
        comparability = {}
    return _format_kv_line(
        *_comparability_identity_tokens(result, comparability),
        ("runtime", comparability.get("runtime_used", result.runtime_used or result.runtime_requested)),
        ("engine", comparability.get("engine_used", result.engine_used or "n/a")),
        ("fallback", comparability.get("fallback_used", result.fallback_used)),
        ("samples", comparability.get("stability_sample_count")),
        ("guard", comparability.get("stability_guard_applied")),
        ("strict", comparability.get("strict_analysis")),
    )


def _meeting_comparability_line(result: Any) -> str:
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    comparability = metadata.get("comparability", {}) if isinstance(metadata, dict) else {}
    if not isinstance(comparability, dict):
        comparability = {}
    routing_mode = comparability.get("routing_mode", getattr(result, "routing_mode", "n/a"))
    rounds_completed = getattr(result, "rounds_completed", 0)
    requested_rounds = getattr(result, "requested_rounds", 0)
    rounds_value = f"{rounds_completed}/{requested_rounds}" if requested_rounds else rounds_completed
    cluster_count = comparability.get("cluster_count", len(getattr(result, "cluster_summaries", []) or []))
    dissent_turn_count = comparability.get("dissent_turn_count", getattr(result, "dissent_turn_count", 0))
    return _format_kv_line(
        *_comparability_identity_tokens(result, comparability),
        ("runtime", comparability.get("runtime_used", metadata.get("runtime_used", "unknown"))),
        ("fallback", comparability.get("fallback_used", metadata.get("fallback_used", False))),
        ("routing", routing_mode),
        ("rounds", rounds_value),
        ("cluster", cluster_count),
        ("dissent", dissent_turn_count),
    )


def _meeting_flow_line(result: Any) -> str | None:
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    meeting_quality = metadata.get("meeting_quality", {}) if isinstance(metadata, dict) else {}
    if not isinstance(meeting_quality, dict):
        meeting_quality = {}
    phases = meeting_quality.get("round_phases") or getattr(result, "round_phases", [])
    if not isinstance(phases, list) or not phases:
        return None
    normalized = [str(phase).strip() for phase in phases if str(phase).strip()]
    if not normalized:
        return None
    return " -> ".join(normalized)


def _deliberation_meeting_line(result: DeliberationResult) -> str | None:
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    meeting_quality = metadata.get("meeting_quality", {}) if isinstance(metadata, dict) else {}
    if not isinstance(meeting_quality, dict) or not meeting_quality:
        return None
    return _format_kv_line(
        ("score", _format_optional_float(meeting_quality.get("quality_score"))),
        ("confidence", _format_optional_float(meeting_quality.get("confidence_score"))),
        ("dissent", meeting_quality.get("dissent_turn_count")),
        ("routing", meeting_quality.get("routing_mode")),
        ("rounds", meeting_quality.get("rounds_completed")),
        ("summary", _shorten_text(meeting_quality.get("summary"), max_length=72)),
    )


def _runtime_resilience_line(result: Any) -> str | None:
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    resilience = metadata.get("runtime_resilience", {}) if isinstance(metadata, dict) else {}
    if not isinstance(resilience, dict) or not resilience:
        return None
    comparability = metadata.get("comparability", {}) if isinstance(metadata, dict) else {}
    if not isinstance(comparability, dict):
        comparability = {}
    note = resilience.get("summary") or resilience.get("message") or resilience.get("note")
    cause = _runtime_resilience_cause(resilience, comparability)
    stage = resilience.get("source_stage") or resilience.get("stage") or comparability.get("runtime_stage")
    stage_count = resilience.get("stage_count") or resilience.get("stages_present")
    return _format_kv_line(
        *_comparability_identity_tokens(result, comparability),
        ("status", resilience.get("status")),
        ("score", _format_optional_float(resilience.get("score"))),
        ("stage", stage),
        ("stages", stage_count),
        ("cause", cause),
        ("runtime", resilience.get("runtime_used") or comparability.get("runtime_used") or getattr(result, "runtime_used", None)),
        ("engine", resilience.get("engine_used") or comparability.get("engine_used") or getattr(result, "engine_used", None)),
        ("fallback", resilience.get("fallback_used", getattr(result, "fallback_used", False))),
        ("attempts", resilience.get("attempt_count") or resilience.get("attempts")),
        ("retries", resilience.get("retry_count") or resilience.get("retries")),
        ("note", _shorten_text(note, max_length=56) if note else None),
    )


def _runtime_resilience_cause(resilience: dict[str, Any], comparability: dict[str, Any]) -> str | None:
    causes: list[str] = []

    degraded_reasons = resilience.get("degraded_reasons")
    if isinstance(degraded_reasons, (list, tuple)):
        causes.extend(str(reason).strip() for reason in degraded_reasons if str(reason).strip())

    if not causes:
        if resilience.get("fallback_count"):
            causes.append("fallback_used")
        if resilience.get("runtime_error_count"):
            causes.append("runtime_error")
        if resilience.get("retry_budget_exhausted"):
            causes.append("retry_budget_exhausted")
        if resilience.get("immediate_fallback"):
            causes.append("immediate_fallback")
        if not causes and (resilience.get("retry_count") or resilience.get("backoff_total_seconds")):
            causes.append("retry/backoff")
        if not causes and bool(comparability.get("stability_guard_applied")) and resilience.get("status") in {"guarded", "degraded"}:
            causes.append("stability_guard")

    if not causes:
        return None

    normalized = [cause for cause in causes[:2] if cause]
    if not normalized:
        return None
    if len(normalized) == 1:
        return normalized[0]
    return ",".join(normalized)


def _format_optional_float(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return None


def _print_harness_inspection(inspection, *, as_json: bool = False) -> None:
    if as_json:
        _print_json(inspection.model_dump(mode="json"))
        return

    console.print(
        Panel(
            f"[bold blue]Snapshot Version:[/bold blue] {inspection.snapshot.version}\n"
            f"[bold blue]Benchmark Suite:[/bold blue] {inspection.benchmark_suite.name} ({inspection.benchmark_suite.suite_version})\n"
            f"[bold blue]Registered Engines:[/bold blue] {', '.join(inspection.registered_engines) if inspection.registered_engines else 'none'}\n"
            f"[bold blue]Engine Backends:[/bold blue] {json.dumps(inspection.registered_backends, sort_keys=True)}\n"
            f"[bold blue]Memory Entries:[/bold blue] {len(inspection.memory_entries)}"
        )
    )

    table = Table(title="Harness Snapshot", show_lines=False)
    table.add_column("Section", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    table.add_row("Workflow Rules", str(len(inspection.snapshot.workflow_rules)))
    table.add_row("Sampling Params", json.dumps(inspection.snapshot.sampling_params, sort_keys=True))
    table.add_row("Skills", ", ".join(sorted(inspection.snapshot.skills.keys())) or "none")
    table.add_row("Config Path", inspection.snapshot.metadata.get("config_path", "n/a"))
    console.print(table)


def _print_harness_round(result, *, as_json: bool = False) -> None:
    if as_json:
        _print_json(result.model_dump(mode="json"))
        return

    console.print(
        Panel(
            f"[bold blue]Round:[/bold blue] {result.round_index}\n"
            f"[bold blue]Decision:[/bold blue] {result.decision.value}\n"
            f"[bold blue]Mode:[/bold blue] {result.mode.value}\n"
            f"[bold blue]Runtime Requested:[/bold blue] {getattr(result, 'runtime_requested', 'n/a')}\n"
            f"[bold blue]Runtime Used:[/bold blue] {getattr(result, 'runtime_used', 'n/a')}\n"
            f"[bold blue]Fallback Used:[/bold blue] {'yes' if getattr(result, 'fallback_used', False) else 'no'}\n"
            f"[bold blue]Baseline Score:[/bold blue] {result.baseline_score:.3f}\n"
            f"[bold blue]Candidate Score:[/bold blue] {result.candidate_score:.3f}\n"
            f"[bold blue]Candidate Snapshot:[/bold blue] {result.candidate_snapshot.version}"
        )
    )

    proposal_table = Table(title="Proposal", show_lines=False)
    proposal_table.add_column("Field", style="cyan", no_wrap=True)
    proposal_table.add_column("Value", style="white")
    proposal_table.add_row("Summary", result.proposal.summary)
    proposal_table.add_row("Risk", result.proposal.risk_level.value)
    proposal_table.add_row(
        "Human Review",
        "yes" if result.requires_human_review else "no",
    )
    proposal_table.add_row(
        "Workflow Additions",
        "\n".join(result.proposal.workflow_rules_to_add) or "none",
    )
    proposal_table.add_row(
        "Sampling Overrides",
        json.dumps(result.proposal.sampling_param_overrides, sort_keys=True) or "{}",
    )
    console.print(proposal_table)

    if result.halted_reason:
        console.print(f"[bold yellow]Halt:[/bold yellow] {result.halted_reason}")


def _print_target_descriptors(targets, *, as_json: bool = False) -> None:
    payload = [target.model_dump(mode="json") for target in targets]
    if as_json:
        _print_json({"targets": payload})
        return

    table = Table(title="Improvement Targets", show_lines=False)
    table.add_column("Target", style="cyan", no_wrap=True)
    table.add_column("Default Mode", style="magenta")
    table.add_column("Description", style="white")
    for target in targets:
        table.add_row(target.target_id, target.default_mode.value, target.description)
    console.print(table)


def _print_improvement_inspection(inspection, *, as_json: bool = False) -> None:
    if as_json:
        _print_json(inspection.model_dump(mode="json"))
        return

    resilience_line = _runtime_resilience_line(inspection)
    panel_body = (
        f"[bold blue]Target:[/bold blue] {inspection.descriptor.target_id}\n"
        f"[bold blue]Description:[/bold blue] {inspection.descriptor.description}\n"
        f"[bold blue]Benchmark Cases:[/bold blue] {len((inspection.benchmark or {}).get('cases', []))}\n"
        f"[bold blue]Memory Entries:[/bold blue] {len(inspection.memory_entries)}\n"
        f"[bold blue]Runtime Requested:[/bold blue] {inspection.metadata.get('runtime_requested', 'n/a')}\n"
        f"[bold blue]Runtime Used:[/bold blue] {inspection.runtime_used.value}\n"
        f"[bold blue]Fallback Used:[/bold blue] {'yes' if inspection.fallback_used else 'no'}"
    )
    if resilience_line:
        panel_body += f"\n[bold blue]Resilience:[/bold blue] {resilience_line}"
    console.print(Panel(panel_body))
    metadata_table = Table(title="Target Metadata", show_lines=False)
    metadata_table.add_column("Field", style="cyan", no_wrap=True)
    metadata_table.add_column("Value", style="white")
    for key, value in sorted(inspection.metadata.items()):
        metadata_table.add_row(key, json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value))
    console.print(metadata_table)


def _print_improvement_round(record, *, as_json: bool = False) -> None:
    if as_json:
        _print_json(record.model_dump(mode="json"))
        return

    resilience_line = _runtime_resilience_line(record)
    panel_body = (
        f"[bold blue]Target:[/bold blue] {record.target_id}\n"
        f"[bold blue]Round:[/bold blue] {record.round_index}\n"
        f"[bold blue]Decision:[/bold blue] {record.decision.value}\n"
        f"[bold blue]Mode:[/bold blue] {record.mode.value}\n"
        f"[bold blue]Runtime Requested:[/bold blue] {record.metadata.get('runtime_requested', 'n/a')}\n"
        f"[bold blue]Runtime Used:[/bold blue] {record.runtime_used.value}\n"
        f"[bold blue]Fallback Used:[/bold blue] {'yes' if record.fallback_used else 'no'}\n"
        f"[bold blue]Baseline Score:[/bold blue] {record.baseline_score:.3f}\n"
        f"[bold blue]Candidate Score:[/bold blue] {record.candidate_score:.3f}"
    )
    if resilience_line:
        panel_body += f"\n[bold blue]Resilience:[/bold blue] {resilience_line}"
    console.print(Panel(panel_body))


def _print_improvement_loop(run, *, as_json: bool = False) -> None:
    if as_json:
        _print_json(run.model_dump(mode="json"))
        return

    console.print(
        Panel(
            f"[bold blue]Target:[/bold blue] {run.target_id}\n"
            f"[bold blue]Mode:[/bold blue] {run.mode.value}\n"
            f"[bold blue]Completed Rounds:[/bold blue] {run.completed_rounds}/{run.max_rounds}\n"
            f"[bold blue]Stopped Reason:[/bold blue] {run.stopped_reason or 'n/a'}"
        )
    )
    if run.rounds:
        last_round = run.rounds[-1]
        resilience_line = _runtime_resilience_line(last_round)
        if resilience_line:
            console.print(f"[bold blue]Resilience:[/bold blue] {resilience_line}")
        console.print(
            f"[bold green]Last Decision:[/bold green] {last_round.decision.value} | "
            f"runtime requested={last_round.metadata.get('runtime_requested', 'n/a')} | "
            f"used={last_round.runtime_used.value} | "
            f"fallback={'yes' if last_round.fallback_used else 'no'}"
        )


def _print_strategy_meeting_result(result, *, as_json: bool = False) -> None:
    if as_json:
        _print_json(result.model_dump(mode="json"))
        return

    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    flow_line = _meeting_flow_line(result)
    quality_line = _format_kv_line(
        ("score", f"{getattr(result, 'quality_score', 0.0):.3f}"),
        ("confidence", f"{getattr(result, 'confidence_score', 0.0):.3f}"),
        ("runtime", metadata.get("runtime_used", "unknown")),
    )
    panel_body = (
        f"[bold blue]Meeting ID:[/bold blue] {result.meeting_id}\n"
        f"[bold blue]Status:[/bold blue] {result.status.value}\n"
        f"[bold blue]Runtime Requested:[/bold blue] {metadata.get('runtime_requested', 'unknown')}\n"
        f"[bold blue]Runtime:[/bold blue] {metadata.get('runtime_used', 'unknown')}\n"
        f"[bold blue]Fallback Used:[/bold blue] {'yes' if metadata.get('fallback_used') else 'no'}\n"
        f"[bold blue]Participants:[/bold blue] {', '.join(result.participants) or 'none'}\n"
        f"[bold blue]Quality:[/bold blue] {quality_line}\n"
        f"[bold blue]Comparability:[/bold blue] {_meeting_comparability_line(result)}"
    )
    resilience_line = _runtime_resilience_line(result)
    if resilience_line:
        panel_body += f"\n[bold blue]Resilience:[/bold blue] {resilience_line}"
    if flow_line:
        panel_body += f"\n[bold blue]Flow:[/bold blue] {flow_line}"
    console.print(Panel(panel_body))
    warnings = _summarize_warning_codes(metadata.get("quality_warnings")) if metadata else "n/a"
    if warnings != "none":
        console.print(f"[bold blue]Warnings:[/bold blue] {warnings}")
    console.print(f"[bold green]Strategy:[/bold green] {result.strategy}")


def _print_deliberation_result(result: DeliberationResult, *, as_json: bool = False) -> None:
    if as_json:
        _print_json(result.model_dump(mode="json"))
        return

    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    stability_line = _deliberation_stability_line(result)
    comparability_line = _deliberation_comparability_line(result)
    meeting_line = _deliberation_meeting_line(result)
    resilience_line = _runtime_resilience_line(result)
    quality_line = _format_kv_line(
        ("judge", f"{getattr(result.judge_scores, 'overall', 0.0):.3f}"),
        ("confidence", f"{result.confidence_level:.3f}"),
        ("engine", result.engine_used or "n/a"),
    )
    console.print(
        Panel(
            (
                f"[bold blue]Deliberation ID:[/bold blue] {result.deliberation_id}\n"
                f"[bold blue]Mode:[/bold blue] {result.mode.value}\n"
                f"[bold blue]Status:[/bold blue] {result.status.value}\n"
                f"[bold blue]Runtime Requested:[/bold blue] {result.runtime_requested}\n"
                f"[bold blue]Runtime Used:[/bold blue] {result.runtime_used or 'n/a'}\n"
                f"[bold blue]Fallback Used:[/bold blue] {'yes' if result.fallback_used else 'no'}\n"
                f"[bold blue]Engine Requested:[/bold blue] {result.engine_requested or 'n/a'}\n"
                f"[bold blue]Engine Used:[/bold blue] {result.engine_used or 'n/a'}\n"
                f"[bold blue]Quality:[/bold blue] {quality_line}\n"
                f"[bold blue]Comparability:[/bold blue] {comparability_line}\n"
                f"[bold blue]Stability:[/bold blue] {stability_line or _format_kv_line(('runs', metadata.get('stability_runs', 'n/a')), ('guard', metadata.get('stability_guard_applied')))}\n"
                + (f"[bold blue]Resilience:[/bold blue] {resilience_line}\n" if resilience_line else "")
                + (f"[bold blue]Meeting:[/bold blue] {meeting_line}\n" if meeting_line else "")
                + f"[bold blue]Ensemble:[/bold blue] {', '.join(result.ensemble_report.compared_engines) if result.ensemble_report else 'disabled'}"
            )
        )
    )
    warnings = _summarize_warning_codes(metadata.get("quality_warnings")) if metadata else "n/a"
    if warnings != "none":
        console.print(f"[bold blue]Warnings:[/bold blue] {warnings}")
    if result.final_strategy:
        console.print(f"[bold green]Final Strategy:[/bold green] {result.final_strategy}")
    elif result.summary:
        console.print(f"[bold green]Summary:[/bold green] {result.summary}")


def _summarize_counter(counts: dict[str, int] | Counter[str]) -> str:
    if not counts:
        return "n/a"
    return ", ".join(f"{name}x{count}" for name, count in sorted(counts.items())) or "n/a"


def _load_deliberation_campaign_report(
    campaign_id: str,
    *,
    output_dir: str | Path | None = None,
) -> DeliberationCampaignReport:
    try:
        return load_deliberation_campaign_report(
            campaign_id,
            output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR,
        )
    except FileNotFoundError as exc:
        raise typer.BadParameter(f"No deliberation campaign report found for {campaign_id!r}.") from exc


def _comparison_report_path(comparison_id: str, *, output_dir: str | Path | None = None) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR)
    return base_dir / comparison_id / "report.json"


def _load_deliberation_campaign_comparison_report(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
) -> DeliberationCampaignComparisonReport:
    helper = getattr(deliberation_campaign_core, "load_deliberation_campaign_comparison_report", None)
    if not callable(helper):
        helper = getattr(deliberation_campaign_core, "read_deliberation_campaign_comparison_report", None)
    if callable(helper):
        try:
            return helper(
                comparison_id,
                output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR,
            )
        except FileNotFoundError as exc:
            raise typer.BadParameter(f"No deliberation campaign comparison found for {comparison_id!r}.") from exc

    report_path = _comparison_report_path(comparison_id, output_dir=output_dir)
    if not report_path.is_file():
        raise typer.BadParameter(f"No deliberation campaign comparison found for {comparison_id!r}.")
    return DeliberationCampaignComparisonReport.model_validate_json(report_path.read_text(encoding="utf-8"))


def _load_deliberation_campaign_comparison_audit(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
    include_markdown: bool = True,
) -> DeliberationCampaignComparisonAudit:
    helper = getattr(deliberation_campaign_core, "load_deliberation_campaign_comparison_audit", None)
    if callable(helper):
        try:
            return helper(
                comparison_id,
                output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR,
                include_markdown=include_markdown,
            )
        except FileNotFoundError as exc:
            raise typer.BadParameter(f"No deliberation campaign comparison audit found for {comparison_id!r}.") from exc

    report = _load_deliberation_campaign_comparison_report(comparison_id, output_dir=output_dir)
    builder = getattr(deliberation_campaign_core, "build_deliberation_campaign_comparison_audit", None)
    if callable(builder):
        return builder(report, include_markdown=include_markdown)
    raise typer.BadParameter("The campaign comparison audit helper is unavailable in this build.")


def _campaign_report_payload(report: DeliberationCampaignReport | dict[str, Any]) -> dict[str, Any]:
    if hasattr(report, "model_dump"):
        return report.model_dump(mode="json")
    return dict(report)


def _campaign_list_payload(report: DeliberationCampaignReport | dict[str, Any]) -> dict[str, Any]:
    payload = _campaign_report_payload(report)
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    return {
        "campaign_id": payload.get("campaign_id", "n/a"),
        "status": payload.get("status", "n/a"),
        "created_at": payload.get("created_at"),
        "topic": payload.get("topic", "n/a"),
        "objective": payload.get("objective"),
        "mode": payload.get("mode", "n/a"),
        "sample_count_requested": payload.get("sample_count_requested", "n/a"),
        "sample_count_completed": summary.get("sample_count_completed", "n/a"),
        "sample_count_failed": summary.get("sample_count_failed", "n/a"),
        "fallback_guard_applied": payload.get("fallback_guard_applied", False),
        "fallback_guard_reason": payload.get("fallback_guard_reason"),
        "report_path": payload.get("report_path"),
        "output_dir": payload.get("output_dir"),
    }


def _comparison_report_payload(report: DeliberationCampaignComparisonReport | dict[str, Any]) -> dict[str, Any]:
    if hasattr(report, "model_dump"):
        return report.model_dump(mode="json")
    return dict(report)


def _comparison_audit_payload(audit: DeliberationCampaignComparisonAudit | dict[str, Any]) -> dict[str, Any]:
    if hasattr(audit, "model_dump"):
        return audit.model_dump(mode="json")
    return dict(audit)


def _comparison_list_payload(report: DeliberationCampaignComparisonReport | dict[str, Any]) -> dict[str, Any]:
    payload = _comparison_report_payload(report)
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    comparison_key_values = summary.get("comparison_key_values", [])
    return {
        "comparison_id": payload.get("comparison_id", "n/a"),
        "created_at": payload.get("created_at"),
        "latest": payload.get("latest"),
        "requested_campaign_ids": payload.get("requested_campaign_ids", []),
        "campaign_count": summary.get("campaign_count", len(payload.get("entries", []))),
        "comparable": summary.get("comparable", True),
        "mismatch_reasons": summary.get("mismatch_reasons", []),
        "comparison_key": comparison_key_values[0] if comparison_key_values else payload.get("metadata", {}).get("comparison_key"),
        "report_path": payload.get("metadata", {}).get("report_path") or payload.get("report_path"),
        "output_dir": payload.get("output_dir"),
    }


def _collect_deliberation_campaign_reports(
    *,
    limit: int = 20,
    output_dir: str | Path | None = None,
    status: DeliberationCampaignStatus | str | None = None,
) -> list[DeliberationCampaignReport | dict[str, Any]]:
    helper = getattr(deliberation_campaign_core, "list_deliberation_campaign_reports", None)
    if not callable(helper):
        helper = getattr(deliberation_campaign_core, "list_deliberation_campaigns", None)
    if callable(helper):
        reports = helper(
            limit=limit,
            status=status,
            output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR,
        )
        if isinstance(reports, dict):
            reports = reports.get("campaigns", reports.get("reports", []))
        return list(reports or [])

    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR)
    report_paths = sorted(
        (path for path in base_dir.glob("*/report.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    collected: list[DeliberationCampaignReport] = []
    selected_status = None if status is None else str(getattr(status, "value", status))
    for report_path in report_paths[: max(0, int(limit))]:
        try:
            report = DeliberationCampaignReport.model_validate_json(report_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if selected_status is not None and str(getattr(report.status, "value", report.status)) != selected_status:
            continue
        collected.append(report)
    return collected


def _collect_deliberation_campaign_comparison_reports(
    *,
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> list[DeliberationCampaignComparisonReport | dict[str, Any]]:
    helper = getattr(deliberation_campaign_core, "list_deliberation_campaign_comparison_reports", None)
    if not callable(helper):
        helper = getattr(deliberation_campaign_core, "list_deliberation_campaign_comparison", None)
    if callable(helper):
        reports = helper(
            limit=limit,
            output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR,
        )
        if isinstance(reports, dict):
            reports = reports.get("comparisons", reports.get("reports", []))
        return list(reports or [])

    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR)
    if not base_dir.exists():
        return []

    report_paths = sorted(
        (path for path in base_dir.glob("*/report.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    collected: list[DeliberationCampaignComparisonReport] = []
    for report_path in report_paths[: max(0, int(limit))]:
        try:
            report = DeliberationCampaignComparisonReport.model_validate_json(report_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        collected.append(report)
    return collected


def _print_deliberation_campaign_result(report: DeliberationCampaignReport | dict[str, Any], *, as_json: bool = False) -> None:
    payload = _campaign_report_payload(report)
    if as_json:
        _print_json(payload)
        return

    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    stability_summary = (
        summary.get("campaign_stability_summary", {})
        if isinstance(summary.get("campaign_stability_summary", {}), dict)
        else {}
    )
    panel_body = (
        f"[bold blue]Campaign ID:[/bold blue] {payload.get('campaign_id', 'n/a')}\n"
        f"[bold blue]Status:[/bold blue] {payload.get('status', 'n/a')}\n"
        f"[bold blue]Topic:[/bold blue] {payload.get('topic', 'n/a')}\n"
        f"[bold blue]Objective:[/bold blue] {payload.get('objective') or 'n/a'}\n"
        f"[bold blue]Samples:[/bold blue] requested={payload.get('sample_count_requested', 'n/a')} | "
        f"completed={summary.get('sample_count_completed', 'n/a')} | "
        f"failed={summary.get('sample_count_failed', 'n/a')} | "
        f"stability_runs={payload.get('stability_runs', 'n/a')} | "
        f"guard={'yes' if payload.get('fallback_guard_applied') else 'no'}"
    )
    guard_reason = payload.get("fallback_guard_reason")
    if guard_reason:
        panel_body += f" | reason={guard_reason}"
    panel_body += (
        f"\n[bold blue]Scores:[/bold blue] mean={float(summary.get('quality_score_mean', 0.0) or 0.0):.3f} "
        f"min={float(summary.get('quality_score_min', 0.0) or 0.0):.3f} "
        f"max={float(summary.get('quality_score_max', 0.0) or 0.0):.3f}"
        f"\n[bold blue]Confidence:[/bold blue] mean={float(summary.get('confidence_level_mean', 0.0) or 0.0):.3f}"
        f"\n[bold blue]Runtime:[/bold blue] {_summarize_counter(summary.get('runtime_counts', {}))}"
        f"\n[bold blue]Engine:[/bold blue] {_summarize_counter(summary.get('engine_counts', {}))}"
        f"\n[bold blue]Stability:[/bold blue] "
        f"{_format_kv_line(('samples', stability_summary.get('sample_count', payload.get('sample_count_requested', 'n/a'))), ('stable', stability_summary.get('stable')), ('std_dev', format(float(stability_summary.get('std_dev', 0.0) or 0.0), '.3f')), ('comparison', stability_summary.get('comparison_key')))}"
    )
    console.print(Panel(panel_body))
    report_path = payload.get("report_path")
    if report_path:
        console.print(f"[bold blue]Report:[/bold blue] {report_path}")
    samples = payload.get("samples", []) if isinstance(payload.get("samples", []), list) else []
    for sample in samples[:5]:
        console.print(
            f"[bold cyan]Sample {sample.get('sample_index', '?')}:[/bold cyan] "
            f"{sample.get('deliberation_id', 'n/a')} | "
            f"score={float(sample.get('quality_score', 0.0) or 0.0):.3f} | "
            f"confidence={float(sample.get('confidence_level', 0.0) or 0.0):.3f} | "
            f"runtime={sample.get('runtime_used', 'n/a')} | "
            f"engine={sample.get('engine_used', 'n/a')} | "
            f"fallback={'yes' if sample.get('fallback_used') else 'no'}"
        )
    if len(samples) > 5:
        console.print(f"[bold cyan]...[/bold cyan] {len(samples) - 5} more samples")


def _print_deliberation_campaign_list(
    reports: list[DeliberationCampaignReport | dict[str, Any]],
    *,
    output_dir: str | Path | None = None,
    limit: int = 20,
    status: DeliberationCampaignStatus | str | None = None,
    as_json: bool = False,
) -> None:
    payload = {
        "count": len(reports),
        "limit": limit,
        "status": None if status is None else str(getattr(status, "value", status)),
        "output_dir": str(Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR)),
        "campaigns": [_campaign_list_payload(report) for report in reports],
    }
    if as_json:
        _print_json(payload)
        return

    console.print(
        Panel(
            f"[bold blue]Output Dir:[/bold blue] {payload['output_dir']}\n"
            f"[bold blue]Count:[/bold blue] {payload['count']} (limit={payload['limit']})\n"
            f"[bold blue]Status Filter:[/bold blue] {payload['status'] or 'all'}"
        )
    )
    table = Table(title="Deliberation Campaigns", show_lines=False)
    table.add_column("Campaign ID", style="cyan", no_wrap=True)
    table.add_column("Status", style="white")
    table.add_column("Created At", style="magenta")
    table.add_column("Samples", style="green")
    table.add_column("Guard", style="yellow")
    table.add_column("Topic", style="white")
    for campaign in payload["campaigns"]:
        table.add_row(
            str(campaign.get("campaign_id", "n/a")),
            str(campaign.get("status", "n/a")),
            str(campaign.get("created_at", "n/a")),
            f"{campaign.get('sample_count_completed', 'n/a')}/{campaign.get('sample_count_requested', 'n/a')}",
            "yes" if campaign.get("fallback_guard_applied") else "no",
            _shorten_text(campaign.get("topic", "n/a"), max_length=32),
        )
    console.print(table)


def _print_deliberation_campaign_comparison_list(
    reports: list[DeliberationCampaignComparisonReport | dict[str, Any]],
    *,
    output_dir: str | Path | None = None,
    limit: int = 20,
    as_json: bool = False,
) -> None:
    payload = {
        "count": len(reports),
        "limit": limit,
        "output_dir": str(Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR)),
        "comparisons": [_comparison_list_payload(report) for report in reports],
    }
    if as_json:
        _print_json(payload)
        return

    console.print(
        Panel(
            f"[bold blue]Output Dir:[/bold blue] {payload['output_dir']}\n"
            f"[bold blue]Count:[/bold blue] {payload['count']} (limit={payload['limit']})"
        )
    )
    table = Table(title="Deliberation Campaign Comparisons", show_lines=False)
    table.add_column("Comparison ID", style="cyan", no_wrap=True)
    table.add_column("Created At", style="magenta")
    table.add_column("Campaigns", style="white")
    table.add_column("Comparable", style="green")
    table.add_column("Mismatch", style="yellow")
    for comparison in payload["comparisons"]:
        requested_ids = comparison.get("requested_campaign_ids", [])
        requested_text = ", ".join(requested_ids) if requested_ids else f"latest={comparison.get('latest', 'n/a')}"
        table.add_row(
            str(comparison.get("comparison_id", "n/a")),
            str(comparison.get("created_at", "n/a")),
            _shorten_text(requested_text, max_length=32),
            "yes" if comparison.get("comparable") else "no",
            _shorten_text(", ".join(comparison.get("mismatch_reasons", [])) or "none", max_length=32),
        )
    console.print(table)


def _print_deliberation_campaign_comparison(
    comparison_report: Any,
    *,
    output_dir: str | Path | None = None,
    as_json: bool = False,
) -> None:
    payload = (
        comparison_report.model_dump(mode="json")
        if hasattr(comparison_report, "model_dump")
        else dict(comparison_report)
    )
    entries = payload.get("entries", []) if isinstance(payload.get("entries"), list) else []
    left_payload = entries[0] if len(entries) >= 1 and isinstance(entries[0], dict) else {}
    right_payload = entries[1] if len(entries) >= 2 and isinstance(entries[1], dict) else {}
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    comparison_mode = "latest" if payload.get("latest") else "explicit"

    def _float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _count_deltas(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
        keys = sorted(set(before) | set(after))
        deltas: dict[str, int] = {}
        for key in keys:
            delta = _int(before.get(key, 0)) - _int(after.get(key, 0))
            if delta:
                deltas[key] = delta
        return deltas

    comparison = {
        "sample_count_completed_delta": _int(left_payload.get("sample_count_completed")) - _int(right_payload.get("sample_count_completed")),
        "sample_count_failed_delta": _int(left_payload.get("sample_count_failed")) - _int(right_payload.get("sample_count_failed")),
        "quality_score_mean_delta": _float(left_payload.get("quality_score_mean")) - _float(right_payload.get("quality_score_mean")),
        "confidence_level_mean_delta": _float(left_payload.get("confidence_level_mean")) - _float(right_payload.get("confidence_level_mean")),
        "fallback_count_delta": _int(left_payload.get("fallback_count")) - _int(right_payload.get("fallback_count")),
        "runtime_count_deltas": _count_deltas(
            left_payload.get("runtime_counts", {}) if isinstance(left_payload.get("runtime_counts"), dict) else {},
            right_payload.get("runtime_counts", {}) if isinstance(right_payload.get("runtime_counts"), dict) else {},
        ),
        "engine_count_deltas": _count_deltas(
            left_payload.get("engine_counts", {}) if isinstance(left_payload.get("engine_counts"), dict) else {},
            right_payload.get("engine_counts", {}) if isinstance(right_payload.get("engine_counts"), dict) else {},
        ),
    }
    formatted_payload = {
        **payload,
        "comparison_mode": comparison_mode,
        "output_dir": str(Path(output_dir or payload.get("output_dir") or DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR)),
        "left": left_payload,
        "right": right_payload,
        "comparison": comparison,
    }
    formatted_payload["comparison"]["metrics"] = [
        {
            "name": "sample_count_completed",
            "left": left_payload.get("sample_count_completed", "n/a"),
            "right": right_payload.get("sample_count_completed", "n/a"),
            "delta": formatted_payload["comparison"]["sample_count_completed_delta"],
        },
        {
            "name": "sample_count_failed",
            "left": left_payload.get("sample_count_failed", "n/a"),
            "right": right_payload.get("sample_count_failed", "n/a"),
            "delta": formatted_payload["comparison"]["sample_count_failed_delta"],
        },
        {
            "name": "quality_score_mean",
            "left": f"{_float(left_payload.get('quality_score_mean')):.3f}",
            "right": f"{_float(right_payload.get('quality_score_mean')):.3f}",
            "delta": f"{formatted_payload['comparison']['quality_score_mean_delta']:+.3f}",
        },
        {
            "name": "confidence_level_mean",
            "left": f"{_float(left_payload.get('confidence_level_mean')):.3f}",
            "right": f"{_float(right_payload.get('confidence_level_mean')):.3f}",
            "delta": f"{formatted_payload['comparison']['confidence_level_mean_delta']:+.3f}",
        },
        {
            "name": "fallback_count",
            "left": left_payload.get("fallback_count", "n/a"),
            "right": right_payload.get("fallback_count", "n/a"),
            "delta": formatted_payload["comparison"]["fallback_count_delta"],
        },
    ]
    if as_json:
        _print_json(formatted_payload)
        return

    panel_body = (
        f"[bold blue]Comparison Mode:[/bold blue] {comparison_mode}\n"
        f"[bold blue]Left:[/bold blue] {left_payload.get('campaign_id', 'n/a')} | "
        f"status={left_payload.get('status', 'n/a')} | "
        f"created_at={left_payload.get('created_at', 'n/a')} | "
        f"samples={left_payload.get('sample_count_completed', 'n/a')}/{left_payload.get('sample_count_requested', 'n/a')} | "
        f"guard={'yes' if left_payload.get('fallback_guard_applied') else 'no'}\n"
        f"[bold blue]Right:[/bold blue] {right_payload.get('campaign_id', 'n/a')} | "
        f"status={right_payload.get('status', 'n/a')} | "
        f"created_at={right_payload.get('created_at', 'n/a')} | "
        f"samples={right_payload.get('sample_count_completed', 'n/a')}/{right_payload.get('sample_count_requested', 'n/a')} | "
        f"guard={'yes' if right_payload.get('fallback_guard_applied') else 'no'}\n"
        f"[bold blue]Delta:[/bold blue] "
        f"samples={formatted_payload['comparison']['sample_count_completed_delta']} | "
        f"failed={formatted_payload['comparison']['sample_count_failed_delta']} | "
        f"quality_mean={formatted_payload['comparison']['quality_score_mean_delta']:+.3f} | "
        f"confidence_mean={formatted_payload['comparison']['confidence_level_mean_delta']:+.3f} | "
        f"fallbacks={formatted_payload['comparison']['fallback_count_delta']:+d}\n"
        f"[bold blue]Comparable:[/bold blue] {'yes' if summary.get('comparable') else 'no'} | "
        f"mismatches={', '.join(summary.get('mismatch_reasons', [])) or 'none'}\n"
        f"[bold blue]Runtime:[/bold blue] "
        f"left={_summarize_counter(left_payload.get('runtime_counts', {}))} | "
        f"right={_summarize_counter(right_payload.get('runtime_counts', {}))}\n"
        f"[bold blue]Engine:[/bold blue] "
        f"left={_summarize_counter(left_payload.get('engine_counts', {}))} | "
        f"right={_summarize_counter(right_payload.get('engine_counts', {}))}"
    )
    console.print(Panel(panel_body))

    table = Table(title="Campaign Comparison", show_lines=False)
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Left", style="white")
    table.add_column("Right", style="white")
    table.add_column("Delta", style="yellow")
    for metric in formatted_payload["comparison"]["metrics"]:
        table.add_row(
            str(metric["name"]),
            str(metric["left"]),
            str(metric["right"]),
            str(metric["delta"]),
    )
    console.print(table)


def _comparison_export_id(comparison_id: str, *, format: str = "markdown") -> str:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    return f"{comparison_id}__{normalized_format}"


def _benchmark_report_id(benchmark_id: str) -> str:
    normalized = str(benchmark_id).strip()
    return normalized or "benchmark"


def _benchmark_report_path(benchmark_id: str, *, output_dir: str | Path | None = None) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR)
    return base_dir / _benchmark_report_id(benchmark_id) / "report.json"


def _benchmark_report_payload(report: dict[str, Any] | Any) -> dict[str, Any]:
    if hasattr(report, "model_dump"):
        return report.model_dump(mode="json")
    return dict(report)


def _load_deliberation_campaign_benchmark_report(
    benchmark_id: str,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any] | DeliberationCampaignBenchmarkBundle:
    helper = getattr(deliberation_campaign_core, "load_deliberation_campaign_benchmark", None)
    if callable(helper):
        try:
            return helper(
                benchmark_id,
                output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR,
            )
        except FileNotFoundError as exc:
            raise typer.BadParameter(f"No deliberation campaign benchmark found for {benchmark_id!r}.") from exc

    report_path = _benchmark_report_path(benchmark_id, output_dir=output_dir)
    if not report_path.is_file():
        raise typer.BadParameter(f"No deliberation campaign benchmark found for {benchmark_id!r}.")
    return json.loads(report_path.read_text(encoding="utf-8"))


def _collect_deliberation_campaign_benchmark_reports(
    *,
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> list[dict[str, Any] | DeliberationCampaignBenchmarkBundle]:
    helper = getattr(deliberation_campaign_core, "list_deliberation_campaign_benchmarks", None)
    if callable(helper):
        try:
            reports = helper(
                limit=limit,
                output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR,
            )
            if isinstance(reports, dict):
                reports = reports.get("benchmarks", reports.get("reports", []))
            return list(reports or [])
        except FileNotFoundError:
            return []

    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR)
    if not base_dir.exists():
        return []

    reports: list[dict[str, Any]] = []
    for report_path in sorted(
        (path for path in base_dir.glob("*/report.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[: max(0, int(limit))]:
        try:
            reports.append(json.loads(report_path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return reports


def _print_deliberation_campaign_benchmark_report(report: dict[str, Any], *, as_json: bool = False) -> None:
    payload = _benchmark_report_payload(report)
    if as_json:
        _print_json(payload)
        return

    baseline_campaign = payload.get("baseline_campaign", {}) if isinstance(payload.get("baseline_campaign", {}), dict) else {}
    candidate_campaign = payload.get("candidate_campaign", {}) if isinstance(payload.get("candidate_campaign", {}), dict) else {}
    comparison = payload.get("comparison", {}) if isinstance(payload.get("comparison", {}), dict) else {}
    export = payload.get("export", {}) if isinstance(payload.get("export", {}), dict) else {}
    panel_body = (
        f"[bold blue]Benchmark ID:[/bold blue] {payload.get('benchmark_id', 'n/a')}\n"
        f"[bold blue]Baseline:[/bold blue] {payload.get('baseline_campaign_id', baseline_campaign.get('campaign_id', 'n/a'))}\n"
        f"[bold blue]Candidate:[/bold blue] {payload.get('candidate_campaign_id', candidate_campaign.get('campaign_id', 'n/a'))}\n"
        f"[bold blue]Comparison ID:[/bold blue] {payload.get('comparison_id', comparison.get('comparison_id', 'n/a'))}\n"
        f"[bold blue]Export ID:[/bold blue] {payload.get('export_id', export.get('export_id', 'n/a'))}\n"
        f"[bold blue]Format:[/bold blue] {payload.get('format', export.get('format', 'n/a'))}"
    )
    console.print(Panel(panel_body))
    if payload.get("report_path"):
        console.print(f"[bold blue]Report:[/bold blue] {payload['report_path']}")


def _print_deliberation_campaign_benchmark_list(
    reports: list[dict[str, Any]],
    *,
    output_dir: str | Path | None = None,
    limit: int = 20,
    as_json: bool = False,
) -> None:
    payload = {
        "count": len(reports),
        "limit": limit,
        "output_dir": str(Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR)),
        "benchmarks": [_benchmark_report_payload(report) for report in reports],
    }
    if as_json:
        _print_json(payload)
        return

    console.print(
        Panel(
            f"[bold blue]Output Dir:[/bold blue] {payload['output_dir']}\n"
            f"[bold blue]Count:[/bold blue] {payload['count']} (limit={payload['limit']})"
        )
    )
    table = Table(title="Deliberation Campaign Benchmarks", show_lines=False)
    table.add_column("Benchmark ID", style="cyan", no_wrap=True)
    table.add_column("Created At", style="magenta")
    table.add_column("Baseline", style="white")
    table.add_column("Candidate", style="white")
    table.add_column("Comparable", style="green")
    table.add_column("Export", style="yellow")
    for benchmark in payload["benchmarks"]:
        comparison = benchmark.get("comparison", {}) if isinstance(benchmark.get("comparison", {}), dict) else {}
        table.add_row(
            str(benchmark.get("benchmark_id", "n/a")),
            str(benchmark.get("created_at", "n/a")),
            str(benchmark.get("baseline_campaign_id", benchmark.get("baseline_campaign", {}).get("campaign_id", "n/a"))),
            str(benchmark.get("candidate_campaign_id", benchmark.get("candidate_campaign", {}).get("campaign_id", "n/a"))),
            "yes" if comparison.get("summary", {}).get("comparable", benchmark.get("comparison", {}).get("comparable", True)) else "no",
            str(benchmark.get("export_id", benchmark.get("export", {}).get("export_id", "n/a"))),
    )
    console.print(table)


def _benchmark_matrix_report_id(matrix_id: str) -> str:
    normalized = str(matrix_id).strip()
    return normalized or "benchmark_matrix"


def _benchmark_matrix_report_path(matrix_id: str, *, output_dir: str | Path | None = None) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR)
    return base_dir / _benchmark_matrix_report_id(matrix_id) / "report.json"


def _benchmark_matrix_report_payload(report: dict[str, Any] | Any) -> dict[str, Any]:
    payload = report.model_dump(mode="json") if hasattr(report, "model_dump") else dict(report)
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
    benchmark_ids: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        candidate_campaign = (
            entry.get("candidate_campaign", {})
            if isinstance(entry.get("candidate_campaign", {}), dict)
            else {}
        )
        candidate_campaign_id = candidate_campaign.get("campaign_id")
        if baseline_campaign_id and candidate_campaign_id:
            benchmark_ids.append(f"{baseline_campaign_id}__vs__{candidate_campaign_id}")
    return {
        **payload,
        "matrix_id": matrix_id,
        "baseline_campaign_id": baseline_campaign_id,
        "candidate_count": summary.get("candidate_count", len(entries)),
        "candidate_campaign_ids": summary.get("candidate_campaign_ids", []),
        "candidate_labels": summary.get("candidate_labels", []),
        "comparison_ids": summary.get("comparison_ids", []),
        "benchmark_ids": benchmark_ids,
        "benchmarks": entries,
    }


def _load_deliberation_campaign_benchmark_matrix_report(
    matrix_id: str,
    *,
    output_dir: str | Path | None = None,
) -> DeliberationCampaignMatrixBenchmarkBundle:
    helper = getattr(deliberation_campaign_core, "load_deliberation_campaign_matrix_benchmark", None)
    if callable(helper):
        try:
            return helper(matrix_id, output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR)
        except FileNotFoundError as exc:
            raise typer.BadParameter(f"No deliberation campaign benchmark matrix found for {matrix_id!r}.") from exc

    report_path = _benchmark_matrix_report_path(matrix_id, output_dir=output_dir)
    if not report_path.is_file():
        raise typer.BadParameter(f"No deliberation campaign benchmark matrix found for {matrix_id!r}.")
    return DeliberationCampaignMatrixBenchmarkBundle.model_validate_json(report_path.read_text(encoding="utf-8"))


def _collect_deliberation_campaign_benchmark_matrix_reports(
    *,
    limit: int | None = None,
    output_dir: str | Path | None = None,
) -> list[DeliberationCampaignMatrixBenchmarkBundle]:
    helper = getattr(deliberation_campaign_core, "list_deliberation_campaign_matrix_benchmarks", None)
    if callable(helper):
        return helper(output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR, limit=limit)

    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR)
    if not base_dir.exists():
        return []

    reports: list[DeliberationCampaignMatrixBenchmarkBundle] = []
    for matrix_dir in base_dir.iterdir():
        if not matrix_dir.is_dir():
            continue
        report_path = matrix_dir / "report.json"
        if not report_path.is_file():
            continue
        try:
            report = DeliberationCampaignMatrixBenchmarkBundle.model_validate_json(
                report_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue
        reports.append(report)

    reports.sort(
        key=lambda report: (
            report.created_at,
            report.benchmark_id,
        ),
        reverse=True,
    )
    if limit is None:
        return reports
    return reports[: max(0, int(limit))]


def _load_deliberation_campaign_benchmark_matrix_comparison_report(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
) -> DeliberationCampaignMatrixBenchmarkComparisonReport:
    helper = getattr(deliberation_campaign_core, "load_deliberation_campaign_matrix_benchmark_comparison_report", None)
    if callable(helper):
        try:
            return helper(
                comparison_id,
                output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR,
            )
        except FileNotFoundError as exc:
            raise typer.BadParameter(
                f"No deliberation campaign benchmark matrix comparison found for {comparison_id!r}."
            ) from exc

    report_path = _matrix_benchmark_comparison_report_path(comparison_id, output_dir=output_dir)
    if not report_path.is_file():
        raise typer.BadParameter(
            f"No deliberation campaign benchmark matrix comparison found for {comparison_id!r}."
        )
    return DeliberationCampaignMatrixBenchmarkComparisonReport.model_validate_json(
        report_path.read_text(encoding="utf-8")
    )


def _collect_deliberation_campaign_benchmark_matrix_comparison_reports(
    *,
    limit: int | None = None,
    output_dir: str | Path | None = None,
) -> list[DeliberationCampaignMatrixBenchmarkComparisonReport]:
    helper = getattr(deliberation_campaign_core, "list_deliberation_campaign_matrix_benchmark_comparison_reports", None)
    if callable(helper):
        return helper(
            output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR,
            limit=limit,
        )

    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR)
    if not base_dir.exists():
        return []

    reports: list[DeliberationCampaignMatrixBenchmarkComparisonReport] = []
    for comparison_dir in base_dir.iterdir():
        if not comparison_dir.is_dir():
            continue
        report_path = comparison_dir / "report.json"
        if not report_path.is_file():
            continue
        try:
            report = DeliberationCampaignMatrixBenchmarkComparisonReport.model_validate_json(
                report_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue
        reports.append(report)

    reports.sort(
        key=lambda report: (
            report.created_at,
            report.comparison_id,
        ),
        reverse=True,
    )
    if limit is None:
        return reports
    return reports[: max(0, int(limit))]


def _matrix_benchmark_comparison_report_id(
    left_matrix_id: str,
    right_matrix_id: str,
    *,
    latest: bool = False,
) -> str:
    left = _benchmark_matrix_report_id(left_matrix_id).replace("/", "_")
    right = _benchmark_matrix_report_id(right_matrix_id).replace("/", "_")
    mode = "latest" if latest else "explicit"
    return f"matrix_benchmark_comparison__{mode}__{left}__vs__{right}"


def _matrix_benchmark_comparison_report_path(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR)
    return base_dir / comparison_id / "report.json"


def _matrix_benchmark_comparison_report_payload(
    report: DeliberationCampaignMatrixBenchmarkComparisonReport | dict[str, Any] | Any,
) -> dict[str, Any]:
    payload = report.model_dump(mode="json") if hasattr(report, "model_dump") else dict(report)
    if (
        isinstance(payload.get("left"), dict)
        and isinstance(payload.get("right"), dict)
        and isinstance(payload.get("comparison"), dict)
    ):
        payload.setdefault("comparison_mode", "latest" if payload.get("latest") else "explicit")
        return payload

    entries = payload.get("entries", []) if isinstance(payload.get("entries", []), list) else []
    left_entry = entries[0] if len(entries) >= 1 and isinstance(entries[0], dict) else {}
    right_entry = entries[1] if len(entries) >= 2 and isinstance(entries[1], dict) else {}
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}

    def _entry_matrix_payload(entry: dict[str, Any]) -> dict[str, Any]:
        baseline_runtime = str(entry.get("baseline_runtime", "")).strip()
        candidate_runtimes = [
            str(value).strip()
            for value in entry.get("candidate_runtimes", [])
            if str(value).strip()
        ] if isinstance(entry.get("candidate_runtimes", []), list) else []
        baseline_engine = str(entry.get("baseline_engine", "")).strip()
        candidate_engines = [
            str(value).strip()
            for value in entry.get("candidate_engines", [])
            if str(value).strip()
        ] if isinstance(entry.get("candidate_engines", []), list) else []
        runtime_values = sorted({value for value in [baseline_runtime, *candidate_runtimes] if value})
        engine_values = sorted({value for value in [baseline_engine, *candidate_engines] if value})
        return {
            "matrix_id": entry.get("benchmark_id"),
            "benchmark_id": entry.get("benchmark_id"),
            "created_at": entry.get("created_at"),
            "baseline_campaign_id": entry.get("baseline_campaign_id"),
            "report_path": entry.get("report_path"),
            "summary": {
                "candidate_count": entry.get("candidate_count", 0),
                "candidate_labels": entry.get("candidate_labels", []),
                "candidate_runtimes": entry.get("candidate_runtimes", []),
                "candidate_engines": entry.get("candidate_engines", []),
                "comparison_ids": entry.get("comparison_ids", []),
                "comparable_count": entry.get("comparable_count", 0),
                "mismatch_count": entry.get("mismatch_count", 0),
                "quality_score_mean": entry.get("quality_score_mean", 0.0),
                "confidence_level_mean": entry.get("confidence_level_mean", 0.0),
                "runtime_values": runtime_values,
                "engine_values": engine_values,
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

    def _delta(left_value: Any, right_value: Any) -> int | float:
        if isinstance(left_value, float) or isinstance(right_value, float):
            return round(_float(left_value) - _float(right_value), 6)
        return _int(left_value) - _int(right_value)

    left_payload = _entry_matrix_payload(left_entry)
    right_payload = _entry_matrix_payload(right_entry)
    left_summary = left_payload.get("summary", {}) if isinstance(left_payload.get("summary", {}), dict) else {}
    right_summary = right_payload.get("summary", {}) if isinstance(right_payload.get("summary", {}), dict) else {}
    comparison = {
        "candidate_count_delta": _delta(left_summary.get("candidate_count"), right_summary.get("candidate_count")),
        "comparable_count_delta": _delta(left_summary.get("comparable_count"), right_summary.get("comparable_count")),
        "mismatch_count_delta": _delta(left_summary.get("mismatch_count"), right_summary.get("mismatch_count")),
        "quality_score_mean_delta": _delta(
            left_summary.get("quality_score_mean"),
            right_summary.get("quality_score_mean"),
        ),
        "confidence_level_mean_delta": _delta(
            left_summary.get("confidence_level_mean"),
            right_summary.get("confidence_level_mean"),
        ),
        "metrics": [
            {
                "name": "candidate_count",
                "left": left_summary.get("candidate_count", 0),
                "right": right_summary.get("candidate_count", 0),
                "delta": _delta(left_summary.get("candidate_count"), right_summary.get("candidate_count")),
            },
            {
                "name": "comparable_count",
                "left": left_summary.get("comparable_count", 0),
                "right": right_summary.get("comparable_count", 0),
                "delta": _delta(left_summary.get("comparable_count"), right_summary.get("comparable_count")),
            },
            {
                "name": "mismatch_count",
                "left": left_summary.get("mismatch_count", 0),
                "right": right_summary.get("mismatch_count", 0),
                "delta": _delta(left_summary.get("mismatch_count"), right_summary.get("mismatch_count")),
            },
            {
                "name": "quality_score_mean",
                "left": f"{_float(left_summary.get('quality_score_mean')):.3f}",
                "right": f"{_float(right_summary.get('quality_score_mean')):.3f}",
                "delta": f"{_delta(left_summary.get('quality_score_mean'), right_summary.get('quality_score_mean')):+.3f}",
            },
            {
                "name": "confidence_level_mean",
                "left": f"{_float(left_summary.get('confidence_level_mean')):.3f}",
                "right": f"{_float(right_summary.get('confidence_level_mean')):.3f}",
                "delta": f"{_delta(left_summary.get('confidence_level_mean'), right_summary.get('confidence_level_mean')):+.3f}",
            },
        ],
    }

    return {
        **payload,
        "comparison_mode": "latest" if payload.get("latest") else "explicit",
        "requested_matrix_ids": payload.get("requested_benchmark_ids", []),
        "left": left_payload,
        "right": right_payload,
        "comparison": comparison,
        "summary": {
            **summary,
            "matrix_count": summary.get("benchmark_count", len(entries)),
            "matrix_ids": summary.get("benchmark_ids", []),
        },
        "metadata": {
            **(payload.get("metadata", {}) if isinstance(payload.get("metadata", {}), dict) else {}),
            "artifact_kind": "matrix_benchmark_comparison",
            "helper_source": "core",
        },
    }


def _call_deliberation_campaign_matrix_benchmark_comparison_helper(
    *,
    matrix_ids: list[str],
    latest: bool,
    output_dir: str | Path | None,
    persist: bool,
    comparison_output_dir: str | Path | None,
) -> Any | None:
    helper = getattr(deliberation_campaign_core, "compare_deliberation_campaign_matrix_benchmarks", None)
    if not callable(helper):
        helper = getattr(deliberation_campaign_core, "compare_deliberation_campaign_matrix_benchmark_reports", None)
    if not callable(helper):
        return None

    try:
        signature = inspect.signature(helper)
    except (TypeError, ValueError):
        return None

    helper_kwargs: dict[str, Any] = {}
    parameters = signature.parameters
    if latest:
        if "latest" in parameters:
            helper_kwargs["latest"] = 2
    else:
        for key in ("matrix_benchmark_ids", "matrix_ids", "benchmark_ids"):
            if key in parameters:
                helper_kwargs[key] = list(matrix_ids)
                break
        else:
            return None
    if "output_dir" in parameters:
        helper_kwargs["output_dir"] = output_dir
    elif "matrix_benchmark_output_dir" in parameters:
        helper_kwargs["matrix_benchmark_output_dir"] = output_dir
    if "persist" in parameters:
        helper_kwargs["persist"] = persist
    if "comparison_output_dir" in parameters:
        helper_kwargs["comparison_output_dir"] = comparison_output_dir

    return helper(**helper_kwargs)


def _build_deliberation_campaign_benchmark_matrix_comparison_report(
    left_report: DeliberationCampaignMatrixBenchmarkBundle | dict[str, Any],
    right_report: DeliberationCampaignMatrixBenchmarkBundle | dict[str, Any],
    *,
    latest: bool = False,
    requested_matrix_ids: list[str] | None = None,
    persist: bool = True,
    comparison_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    left_payload = _benchmark_matrix_report_payload(left_report)
    right_payload = _benchmark_matrix_report_payload(right_report)
    left_summary = left_payload.get("summary", {}) if isinstance(left_payload.get("summary", {}), dict) else {}
    right_summary = right_payload.get("summary", {}) if isinstance(right_payload.get("summary", {}), dict) else {}

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

    def _normalized_list(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized: list[str] = []
        for value in values:
            text = str(value).strip()
            if text:
                normalized.append(text)
        return normalized

    left_matrix_id = str(left_payload.get("matrix_id", left_payload.get("benchmark_id", "left_matrix")))
    right_matrix_id = str(right_payload.get("matrix_id", right_payload.get("benchmark_id", "right_matrix")))
    left_baseline_campaign_id = str(left_payload.get("baseline_campaign_id", ""))
    right_baseline_campaign_id = str(right_payload.get("baseline_campaign_id", ""))
    left_candidate_campaign_ids = _normalized_list(left_summary.get("candidate_campaign_ids", left_payload.get("candidate_campaign_ids", [])))
    right_candidate_campaign_ids = _normalized_list(right_summary.get("candidate_campaign_ids", right_payload.get("candidate_campaign_ids", [])))
    left_candidate_labels = _normalized_list(left_summary.get("candidate_labels", left_payload.get("candidate_labels", [])))
    right_candidate_labels = _normalized_list(right_summary.get("candidate_labels", right_payload.get("candidate_labels", [])))
    left_runtime_values = sorted(set(_normalized_list(left_summary.get("runtime_values", []))))
    right_runtime_values = sorted(set(_normalized_list(right_summary.get("runtime_values", []))))
    left_engine_values = sorted(set(_normalized_list(left_summary.get("engine_values", []))))
    right_engine_values = sorted(set(_normalized_list(right_summary.get("engine_values", []))))

    mismatch_reasons: list[str] = []
    if left_baseline_campaign_id != right_baseline_campaign_id:
        mismatch_reasons.append("baseline_campaign_mismatch")
    if _int(left_summary.get("candidate_count")) != _int(right_summary.get("candidate_count")):
        mismatch_reasons.append("candidate_count_mismatch")
    if left_candidate_campaign_ids != right_candidate_campaign_ids:
        mismatch_reasons.append("candidate_campaign_mismatch")
    if left_candidate_labels != right_candidate_labels:
        mismatch_reasons.append("candidate_label_mismatch")
    if left_runtime_values != right_runtime_values:
        mismatch_reasons.append("runtime_mismatch")
    if left_engine_values != right_engine_values:
        mismatch_reasons.append("engine_mismatch")
    comparable = not mismatch_reasons

    shared_candidate_campaign_ids = [item for item in left_candidate_campaign_ids if item in set(right_candidate_campaign_ids)]
    comparison = {
        "candidate_count_delta": _int(left_summary.get("candidate_count")) - _int(right_summary.get("candidate_count")),
        "comparable_count_delta": _int(left_summary.get("comparable_count")) - _int(right_summary.get("comparable_count")),
        "mismatch_count_delta": _int(left_summary.get("mismatch_count")) - _int(right_summary.get("mismatch_count")),
        "quality_score_mean_delta": _float(left_summary.get("quality_score_mean")) - _float(right_summary.get("quality_score_mean")),
        "confidence_level_mean_delta": _float(left_summary.get("confidence_level_mean")) - _float(right_summary.get("confidence_level_mean")),
        "shared_candidate_campaign_ids": shared_candidate_campaign_ids,
        "left_only_candidate_campaign_ids": [item for item in left_candidate_campaign_ids if item not in set(right_candidate_campaign_ids)],
        "right_only_candidate_campaign_ids": [item for item in right_candidate_campaign_ids if item not in set(left_candidate_campaign_ids)],
    }
    comparison["metrics"] = [
        {
            "name": "candidate_count",
            "left": _int(left_summary.get("candidate_count")),
            "right": _int(right_summary.get("candidate_count")),
            "delta": comparison["candidate_count_delta"],
        },
        {
            "name": "comparable_count",
            "left": _int(left_summary.get("comparable_count")),
            "right": _int(right_summary.get("comparable_count")),
            "delta": comparison["comparable_count_delta"],
        },
        {
            "name": "mismatch_count",
            "left": _int(left_summary.get("mismatch_count")),
            "right": _int(right_summary.get("mismatch_count")),
            "delta": comparison["mismatch_count_delta"],
        },
        {
            "name": "quality_score_mean",
            "left": f"{_float(left_summary.get('quality_score_mean')):.3f}",
            "right": f"{_float(right_summary.get('quality_score_mean')):.3f}",
            "delta": f"{comparison['quality_score_mean_delta']:+.3f}",
        },
        {
            "name": "confidence_level_mean",
            "left": f"{_float(left_summary.get('confidence_level_mean')):.3f}",
            "right": f"{_float(right_summary.get('confidence_level_mean')):.3f}",
            "delta": f"{comparison['confidence_level_mean_delta']:+.3f}",
        },
    ]

    comparison_id = _matrix_benchmark_comparison_report_id(left_matrix_id, right_matrix_id, latest=latest)
    report_path = _matrix_benchmark_comparison_report_path(comparison_id, output_dir=comparison_output_dir)
    formatted_payload = {
        "comparison_id": comparison_id,
        "comparison_mode": "latest" if latest else "explicit",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "requested_matrix_ids": list(requested_matrix_ids or []),
        "latest": 2 if latest else None,
        "output_dir": str(
            Path(comparison_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR)
        ),
        "report_path": str(report_path) if persist else None,
        "entries": [left_payload, right_payload],
        "left": left_payload,
        "right": right_payload,
        "summary": {
            "matrix_count": 2,
            "matrix_ids": [left_matrix_id, right_matrix_id],
            "baseline_campaign_ids": [left_baseline_campaign_id, right_baseline_campaign_id],
            "candidate_count_values": [
                _int(left_summary.get("candidate_count")),
                _int(right_summary.get("candidate_count")),
            ],
            "shared_candidate_count": len(shared_candidate_campaign_ids),
            "comparable": comparable,
            "mismatch_reasons": mismatch_reasons,
            "runtime_values": sorted(set(left_runtime_values + right_runtime_values)),
            "engine_values": sorted(set(left_engine_values + right_engine_values)),
        },
        "comparison": comparison,
        "metadata": {
            "artifact_kind": "matrix_benchmark_comparison",
            "helper_source": "cli_fallback",
            "left_matrix_id": left_matrix_id,
            "right_matrix_id": right_matrix_id,
        },
    }
    if persist:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(formatted_payload, indent=2, sort_keys=True), encoding="utf-8")
    return formatted_payload


def _compare_deliberation_campaign_benchmark_matrices(
    *,
    matrix_ids: list[str],
    latest: bool,
    output_dir: str | Path | None,
    persist: bool,
    comparison_output_dir: str | Path | None,
) -> dict[str, Any] | Any:
    helper_result = _call_deliberation_campaign_matrix_benchmark_comparison_helper(
        matrix_ids=matrix_ids,
        latest=latest,
        output_dir=output_dir,
        persist=persist,
        comparison_output_dir=comparison_output_dir,
    )
    if helper_result is not None:
        return helper_result

    if latest:
        reports = _collect_deliberation_campaign_benchmark_matrix_reports(limit=2, output_dir=output_dir)
        if len(reports) < 2:
            raise typer.BadParameter("Need at least two persisted matrix benchmarks to use --latest.")
        selected_reports = reports[:2]
        selected_ids = [
            str(_benchmark_matrix_report_payload(report).get("matrix_id", _benchmark_matrix_report_payload(report).get("benchmark_id", "n/a")))
            for report in selected_reports
        ]
    else:
        if len(matrix_ids) != 2:
            raise typer.BadParameter("Provide exactly two matrix benchmark IDs, or use --latest.")
        selected_reports = [
            _load_deliberation_campaign_benchmark_matrix_report(matrix_ids[0], output_dir=output_dir),
            _load_deliberation_campaign_benchmark_matrix_report(matrix_ids[1], output_dir=output_dir),
        ]
        selected_ids = list(matrix_ids)

    return _build_deliberation_campaign_benchmark_matrix_comparison_report(
        selected_reports[0],
        selected_reports[1],
        latest=latest,
        requested_matrix_ids=selected_ids,
        persist=persist,
        comparison_output_dir=comparison_output_dir,
    )


def _print_deliberation_campaign_benchmark_matrix_comparison(
    comparison_report: dict[str, Any] | Any,
    *,
    as_json: bool = False,
) -> None:
    payload = _matrix_benchmark_comparison_report_payload(comparison_report)
    entries = payload.get("entries", []) if isinstance(payload.get("entries", []), list) else []
    left_payload = payload.get("left", entries[0] if len(entries) >= 1 and isinstance(entries[0], dict) else {})
    right_payload = payload.get("right", entries[1] if len(entries) >= 2 and isinstance(entries[1], dict) else {})
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    comparison = payload.get("comparison", {}) if isinstance(payload.get("comparison", {}), dict) else {}
    if as_json:
        _print_json(payload)
        return

    left_summary = left_payload.get("summary", {}) if isinstance(left_payload.get("summary", {}), dict) else {}
    right_summary = right_payload.get("summary", {}) if isinstance(right_payload.get("summary", {}), dict) else {}
    panel_body = (
        f"[bold blue]Comparison Mode:[/bold blue] {payload.get('comparison_mode', 'n/a')}\n"
        f"[bold blue]Left:[/bold blue] {left_payload.get('matrix_id', left_payload.get('benchmark_id', 'n/a'))} | "
        f"baseline={left_payload.get('baseline_campaign_id', 'n/a')} | "
        f"candidates={left_summary.get('candidate_count', 'n/a')} | "
        f"comparable={left_summary.get('comparable_count', 'n/a')} | "
        f"mismatch={left_summary.get('mismatch_count', 'n/a')}\n"
        f"[bold blue]Right:[/bold blue] {right_payload.get('matrix_id', right_payload.get('benchmark_id', 'n/a'))} | "
        f"baseline={right_payload.get('baseline_campaign_id', 'n/a')} | "
        f"candidates={right_summary.get('candidate_count', 'n/a')} | "
        f"comparable={right_summary.get('comparable_count', 'n/a')} | "
        f"mismatch={right_summary.get('mismatch_count', 'n/a')}\n"
        f"[bold blue]Delta:[/bold blue] "
        f"candidates={comparison.get('candidate_count_delta', 'n/a')} | "
        f"comparable={comparison.get('comparable_count_delta', 'n/a')} | "
        f"mismatch={comparison.get('mismatch_count_delta', 'n/a')} | "
        f"quality_mean={float(comparison.get('quality_score_mean_delta', 0.0) or 0.0):+.3f} | "
        f"confidence_mean={float(comparison.get('confidence_level_mean_delta', 0.0) or 0.0):+.3f}\n"
        f"[bold blue]Comparable:[/bold blue] {'yes' if summary.get('comparable') else 'no'} | "
        f"mismatches={', '.join(summary.get('mismatch_reasons', [])) or 'none'}"
    )
    console.print(Panel(panel_body))
    if payload.get("report_path"):
        console.print(f"[bold blue]Report:[/bold blue] {payload['report_path']}")

    table = Table(title="Matrix Benchmark Comparison", show_lines=False)
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Left", style="white")
    table.add_column("Right", style="white")
    table.add_column("Delta", style="yellow")
    for metric in comparison.get("metrics", []):
        if not isinstance(metric, dict):
            continue
        table.add_row(
            str(metric.get("name", "n/a")),
            str(metric.get("left", "n/a")),
            str(metric.get("right", "n/a")),
            str(metric.get("delta", "n/a")),
        )
    console.print(table)


def _print_deliberation_campaign_benchmark_matrix_comparison_list(
    reports: list[DeliberationCampaignMatrixBenchmarkComparisonReport | dict[str, Any]],
    *,
    output_dir: str | Path | None = None,
    limit: int = 20,
    as_json: bool = False,
) -> None:
    payload = {
        "count": len(reports),
        "limit": limit,
        "output_dir": str(
            Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR)
        ),
        "comparisons": [_matrix_benchmark_comparison_report_payload(report) for report in reports],
    }
    if as_json:
        _print_json(payload)
        return

    console.print(
        Panel(
            f"[bold blue]Output Dir:[/bold blue] {payload['output_dir']}\n"
            f"[bold blue]Count:[/bold blue] {payload['count']} (limit={payload['limit']})"
        )
    )
    table = Table(title="Deliberation Campaign Benchmark Matrix Comparisons", show_lines=False)
    table.add_column("Comparison ID", style="cyan", no_wrap=True)
    table.add_column("Created At", style="magenta")
    table.add_column("Left", style="white")
    table.add_column("Right", style="white")
    table.add_column("Comparable", style="green")
    table.add_column("Report", style="yellow")
    for comparison in payload["comparisons"]:
        left_payload = comparison.get("left", {}) if isinstance(comparison.get("left", {}), dict) else {}
        right_payload = comparison.get("right", {}) if isinstance(comparison.get("right", {}), dict) else {}
        summary = comparison.get("summary", {}) if isinstance(comparison.get("summary", {}), dict) else {}
        table.add_row(
            str(comparison.get("comparison_id", "n/a")),
            str(comparison.get("created_at", "n/a")),
            str(left_payload.get("matrix_id", left_payload.get("benchmark_id", "n/a"))),
            str(right_payload.get("matrix_id", right_payload.get("benchmark_id", "n/a"))),
            "yes" if summary.get("comparable", False) else "no",
            str(comparison.get("report_path", "n/a")),
        )
    console.print(table)


def _matrix_benchmark_comparison_audit_payload(
    audit: DeliberationCampaignMatrixBenchmarkComparisonAudit | dict[str, Any],
) -> dict[str, Any]:
    if hasattr(audit, "model_dump"):
        return audit.model_dump(mode="json")
    return dict(audit)


def _matrix_benchmark_comparison_export_id(comparison_id: str, *, format: str = "markdown") -> str:
    normalized_format = str(format).strip().lower() or "markdown"
    return f"{comparison_id}__{normalized_format}"


def _matrix_benchmark_comparison_export_dir(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
) -> Path:
    base_dir = Path(output_dir or CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR)
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
    extension = ".md" if str(format).strip().lower() != "json" else ".json"
    return _matrix_benchmark_comparison_export_dir(export_id, output_dir=output_dir) / f"content{extension}"


def _load_deliberation_campaign_benchmark_matrix_comparison_audit(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
    include_markdown: bool = True,
) -> DeliberationCampaignMatrixBenchmarkComparisonAudit:
    helper = getattr(deliberation_campaign_core, "load_deliberation_campaign_matrix_benchmark_comparison_audit", None)
    if callable(helper):
        try:
            return helper(
                comparison_id,
                output_dir=output_dir or CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR,
                include_markdown=include_markdown,
            )
        except FileNotFoundError as exc:
            raise typer.BadParameter(
                f"No deliberation campaign benchmark matrix comparison audit found for {comparison_id!r}."
            ) from exc

    report = _load_deliberation_campaign_benchmark_matrix_comparison_report(
        comparison_id,
        output_dir=output_dir,
    )
    builder = getattr(deliberation_campaign_core, "build_deliberation_campaign_matrix_benchmark_comparison_audit", None)
    if callable(builder):
        return builder(report, include_markdown=include_markdown)
    raise typer.BadParameter("The matrix benchmark comparison audit helper is unavailable in this build.")


def _load_deliberation_campaign_benchmark_matrix_comparison_export(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
    include_content: bool = True,
) -> DeliberationCampaignMatrixBenchmarkComparisonExport:
    helper = getattr(deliberation_campaign_core, "load_deliberation_campaign_matrix_benchmark_comparison_export", None)
    if callable(helper):
        try:
            return helper(
                export_id,
                output_dir=output_dir or CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR,
                include_content=include_content,
            )
        except FileNotFoundError as exc:
            raise typer.BadParameter(
                f"No deliberation campaign benchmark matrix comparison export found for {export_id!r}."
            ) from exc

    manifest_path = _matrix_benchmark_comparison_export_manifest_path(export_id, output_dir=output_dir)
    if not manifest_path.is_file():
        raise typer.BadParameter(f"No deliberation campaign benchmark matrix comparison export found for {export_id!r}.")
    export = DeliberationCampaignMatrixBenchmarkComparisonExport.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    if include_content and export.content_path:
        content_path = Path(export.content_path)
        if content_path.is_file():
            export.content = content_path.read_text(encoding="utf-8")
    return export


def _materialize_deliberation_campaign_benchmark_matrix_comparison_export(
    comparison_id: str,
    audit: DeliberationCampaignMatrixBenchmarkComparisonAudit | dict[str, Any],
    *,
    output_dir: str | Path | None = None,
    format: str = "markdown",
    export_id: str | None = None,
) -> DeliberationCampaignMatrixBenchmarkComparisonExport:
    normalized_format = str(format).strip().lower() or "markdown"
    helper = getattr(
        deliberation_campaign_core,
        "materialize_deliberation_campaign_matrix_benchmark_comparison_export",
        None,
    )
    if callable(helper):
        try:
            return helper(
                audit,
                format=normalized_format,
                output_dir=output_dir or CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR,
                export_id=export_id or _matrix_benchmark_comparison_export_id(comparison_id, format=normalized_format),
            )
        except FileNotFoundError as exc:
            raise typer.BadParameter(
                f"Unable to persist matrix benchmark comparison export for {comparison_id!r}."
            ) from exc

    audit_payload = _matrix_benchmark_comparison_audit_payload(audit)
    export = DeliberationCampaignMatrixBenchmarkComparisonExport(
        export_id=export_id or _matrix_benchmark_comparison_export_id(comparison_id, format=normalized_format),
        comparison_id=comparison_id,
        format=normalized_format,
        comparison_report_path=audit_payload.get("report_path"),
        output_dir=str(output_dir or CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR),
        benchmark_count=int(audit_payload.get("benchmark_count", 0) or 0),
        benchmark_ids=list(audit_payload.get("benchmark_ids", []))
        if isinstance(audit_payload.get("benchmark_ids", []), list)
        else [],
        content=(
            audit_payload.get("markdown")
            if normalized_format == "markdown"
            else json.dumps(audit_payload, indent=2, sort_keys=True)
        ),
        content_path="",
        manifest_path="",
        comparable=audit_payload.get("comparable", True),
        mismatch_reasons=list(audit_payload.get("mismatch_reasons", [])),
        metadata=audit_payload.get("metadata", {}) if isinstance(audit_payload.get("metadata", {}), dict) else {},
    )
    export_dir = _matrix_benchmark_comparison_export_dir(export.export_id, output_dir=output_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    export.manifest_path = str(_matrix_benchmark_comparison_export_manifest_path(export.export_id, output_dir=output_dir))
    export.content_path = str(
        _matrix_benchmark_comparison_export_content_path(
            export.export_id,
            output_dir=output_dir,
            format=normalized_format,
        )
    )
    export.metadata["manifest_path"] = export.manifest_path
    export.metadata["content_path"] = export.content_path
    export.metadata["persisted"] = True
    Path(export.manifest_path).write_text(
        json.dumps(export.model_dump(mode="json", exclude={"content"}), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if export.content is not None:
        Path(export.content_path).write_text(export.content, encoding="utf-8")
    return export


def _matrix_benchmark_comparison_export_payload(
    export_payload: DeliberationCampaignMatrixBenchmarkComparisonExport | dict[str, Any],
) -> dict[str, Any]:
    if hasattr(export_payload, "model_dump"):
        return export_payload.model_dump(mode="json")
    return dict(export_payload)


def _collect_deliberation_campaign_benchmark_matrix_comparison_exports(
    *,
    limit: int | None = None,
    output_dir: str | Path | None = None,
) -> list[DeliberationCampaignMatrixBenchmarkComparisonExport]:
    helper = getattr(deliberation_campaign_core, "list_deliberation_campaign_matrix_benchmark_comparison_exports", None)
    if callable(helper):
        return helper(
            output_dir=output_dir or CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR,
            limit=limit,
        )

    base_dir = Path(output_dir or CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR)
    if not base_dir.exists():
        return []

    exports: list[DeliberationCampaignMatrixBenchmarkComparisonExport] = []
    for export_dir in base_dir.iterdir():
        if not export_dir.is_dir():
            continue
        manifest_path = export_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            export = DeliberationCampaignMatrixBenchmarkComparisonExport.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue
        exports.append(export)

    exports.sort(
        key=lambda export: (
            export.created_at,
            export.export_id,
        ),
        reverse=True,
    )
    if limit is None:
        return exports
    return exports[: max(0, int(limit))]


def _print_deliberation_campaign_benchmark_matrix_comparison_audit(
    audit: DeliberationCampaignMatrixBenchmarkComparisonAudit | dict[str, Any],
    *,
    as_json: bool = False,
) -> None:
    payload = _matrix_benchmark_comparison_audit_payload(audit)
    if as_json:
        _print_json(payload)
        return
    markdown = str(payload.get("markdown", "")).strip()
    console.print(
        Panel(
            f"[bold blue]Comparison ID:[/bold blue] {payload.get('comparison_id', 'n/a')}\n"
            f"[bold blue]Benchmark Count:[/bold blue] {payload.get('benchmark_count', 'n/a')}\n"
            f"[bold blue]Comparable:[/bold blue] {payload.get('comparable', 'n/a')}\n"
            f"[bold blue]Mismatch Reasons:[/bold blue] {', '.join(payload.get('mismatch_reasons', [])) or 'n/a'}\n"
            f"[bold blue]Report Path:[/bold blue] {payload.get('report_path', 'n/a')}"
        )
    )
    if markdown:
        console.print(markdown)


def _print_deliberation_campaign_benchmark_matrix_comparison_export(
    export: DeliberationCampaignMatrixBenchmarkComparisonExport | dict[str, Any],
    *,
    as_json: bool = False,
) -> None:
    payload = _matrix_benchmark_comparison_export_payload(export)
    if as_json:
        _print_json(payload)
        return
    console.print(
        Panel(
            f"[bold blue]Export ID:[/bold blue] {payload.get('export_id', 'n/a')}\n"
            f"[bold blue]Comparison ID:[/bold blue] {payload.get('comparison_id', 'n/a')}\n"
            f"[bold blue]Format:[/bold blue] {payload.get('format', 'n/a')}\n"
            f"[bold blue]Manifest:[/bold blue] {payload.get('manifest_path', 'n/a')}\n"
            f"[bold blue]Content:[/bold blue] {payload.get('content_path', 'n/a')}"
        )
    )


def _print_deliberation_campaign_benchmark_matrix_comparison_export_list(
    exports: list[DeliberationCampaignMatrixBenchmarkComparisonExport | dict[str, Any]],
    *,
    output_dir: str | Path | None,
    limit: int,
    as_json: bool = False,
) -> None:
    payload = {
        "count": len(exports),
        "limit": limit,
        "output_dir": str(Path(output_dir or CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR)),
        "exports": [_matrix_benchmark_comparison_export_payload(export) for export in exports],
    }
    if as_json:
        _print_json(payload)
        return

    console.print(
        Panel(
            f"[bold blue]Output Dir:[/bold blue] {payload['output_dir']}\n"
            f"[bold blue]Count:[/bold blue] {payload['count']} (limit={payload['limit']})"
        )
    )
    table = Table(title="Matrix Benchmark Comparison Exports", show_lines=False)
    table.add_column("Export ID", style="cyan", no_wrap=True)
    table.add_column("Comparison ID", style="white")
    table.add_column("Format", style="green")
    table.add_column("Created At", style="yellow")
    table.add_column("Content Path", style="magenta")
    for export in payload["exports"]:
        table.add_row(
            str(export.get("export_id", "n/a")),
            str(export.get("comparison_id", "n/a")),
            str(export.get("format", "n/a")),
            str(export.get("created_at", "n/a")),
            _shorten_text(str(export.get("content_path", "n/a")), max_length=48),
        )
    console.print(table)


def _print_deliberation_campaign_benchmark_matrix_report(
    report: DeliberationCampaignMatrixBenchmarkBundle | dict[str, Any],
    *,
    as_json: bool = False,
) -> None:
    payload = _benchmark_matrix_report_payload(report)
    if as_json:
        _print_json(payload)
        return

    entries = payload.get("entries", []) if isinstance(payload.get("entries", []), list) else []
    baseline_campaign = payload.get("baseline_campaign", {}) if isinstance(payload.get("baseline_campaign", {}), dict) else {}
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    panel_body = (
        f"[bold blue]Matrix ID:[/bold blue] {payload.get('matrix_id', 'n/a')}\n"
        f"[bold blue]Baseline:[/bold blue] {payload.get('baseline_campaign_id', baseline_campaign.get('campaign_id', 'n/a'))}\n"
        f"[bold blue]Candidates:[/bold blue] {summary.get('candidate_count', len(entries))}\n"
        f"[bold blue]Comparable:[/bold blue] {summary.get('comparable_count', 'n/a')}\n"
        f"[bold blue]Report:[/bold blue] {payload.get('report_path', 'n/a')}\n"
        f"[bold blue]Output Dir:[/bold blue] {payload.get('output_dir', 'n/a')}"
    )
    console.print(Panel(panel_body))
    table = Table(title="Deliberation Campaign Benchmark Matrix", show_lines=False)
    table.add_column("Index", style="cyan", no_wrap=True)
    table.add_column("Candidate", style="white")
    table.add_column("Comparable", style="green")
    table.add_column("Comparison", style="cyan", no_wrap=True)
    table.add_column("Export", style="yellow")
    for index, entry in enumerate(entries, start=1):
        candidate_spec = entry.get("candidate_spec", {}) if isinstance(entry.get("candidate_spec", {}), dict) else {}
        candidate_campaign = entry.get("candidate_campaign", {}) if isinstance(entry.get("candidate_campaign", {}), dict) else {}
        comparison_bundle = entry.get("comparison_bundle", {}) if isinstance(entry.get("comparison_bundle", {}), dict) else {}
        comparison_report = (
            comparison_bundle.get("comparison_report", {})
            if isinstance(comparison_bundle.get("comparison_report", {}), dict)
            else {}
        )
        comparison_summary = (
            comparison_report.get("summary", {})
            if isinstance(comparison_report.get("summary", {}), dict)
            else {}
        )
        candidate_label = (
            candidate_spec.get("label")
            or candidate_spec.get("campaign_id")
            or candidate_campaign.get("campaign_id", "n/a")
        )
        table.add_row(
            str(index),
            str(candidate_label),
            "yes" if comparison_summary.get("comparable", True) else "no",
            str(comparison_report.get("comparison_id", comparison_bundle.get("comparison_report", {}).get("comparison_id", "n/a"))),
            str(comparison_bundle.get("export", {}).get("export_id", "n/a")),
        )
    console.print(table)


def _benchmark_matrix_audit_report_id(matrix_id: str) -> str:
    return f"matrix_benchmark_audit__{_benchmark_matrix_report_id(matrix_id)}"


def _benchmark_matrix_audit_report_path(
    matrix_id: str,
    *,
    output_dir: str | Path | None = None,
) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR)
    return base_dir / _benchmark_matrix_audit_report_id(matrix_id) / "report.json"


def _benchmark_matrix_export_id(matrix_id: str, *, format: str = "markdown") -> str:
    normalized_format = str(format).strip().lower() or "markdown"
    return f"{_benchmark_matrix_audit_report_id(matrix_id)}__{normalized_format}"


def _benchmark_matrix_export_dir(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR)
    return base_dir / export_id


def _benchmark_matrix_export_manifest_path(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
) -> Path:
    return _benchmark_matrix_export_dir(export_id, output_dir=output_dir) / "manifest.json"


def _benchmark_matrix_export_content_path(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> Path:
    normalized_format = str(format).strip().lower() or "markdown"
    extension = "md" if normalized_format == "markdown" else "json"
    return _benchmark_matrix_export_dir(export_id, output_dir=output_dir) / f"content.{extension}"


def _benchmark_matrix_audit_candidate_payload(
    entry: dict[str, Any],
    *,
    rank: int,
) -> dict[str, Any]:
    def _text(value: Any) -> str:
        normalized = value.value if hasattr(value, "value") else value
        text = str(normalized).strip()
        return text or "n/a"

    candidate_spec = (
        entry.get("candidate_spec", {}) if isinstance(entry.get("candidate_spec", {}), dict) else {}
    )
    candidate_campaign = (
        entry.get("candidate_campaign", {}) if isinstance(entry.get("candidate_campaign", {}), dict) else {}
    )
    comparison_bundle = (
        entry.get("comparison_bundle", {}) if isinstance(entry.get("comparison_bundle", {}), dict) else {}
    )
    comparison_report = (
        comparison_bundle.get("comparison_report", {})
        if isinstance(comparison_bundle.get("comparison_report", {}), dict)
        else {}
    )
    comparison_summary = (
        comparison_report.get("summary", {})
        if isinstance(comparison_report.get("summary", {}), dict)
        else {}
    )
    candidate_label = _text(entry.get("candidate_label") or candidate_spec.get("label") or candidate_campaign.get("campaign_id"))
    candidate_campaign_id = _text(
        entry.get("candidate_campaign_id")
        or candidate_campaign.get("campaign_id")
        or candidate_spec.get("campaign_id")
    )
    runtime_value = _text(
        candidate_spec.get("runtime")
        or entry.get("candidate_runtime")
        or candidate_campaign.get("runtime_requested")
        or candidate_campaign.get("runtime_used")
    )
    engine_value = _text(
        candidate_spec.get("engine_preference")
        or entry.get("candidate_engine_preference")
        or candidate_campaign.get("engine_requested")
        or candidate_campaign.get("engine_used")
    )
    mismatch_reasons = (
        comparison_summary.get("mismatch_reasons", [])
        if isinstance(comparison_summary.get("mismatch_reasons", []), list)
        else []
    )
    return {
        "rank": rank,
        "candidate_index": entry.get("candidate_index", rank),
        "candidate_label": candidate_label,
        "candidate_campaign_id": candidate_campaign_id,
        "runtime": runtime_value,
        "engine": engine_value,
        "comparable": bool(comparison_summary.get("comparable", True)),
        "quality_score_mean": float(comparison_summary.get("quality_score_mean", 0.0) or 0.0),
        "confidence_level_mean": float(comparison_summary.get("confidence_level_mean", 0.0) or 0.0),
        "comparison_id": str(comparison_report.get("comparison_id", "n/a")),
        "export_id": str(comparison_bundle.get("export", {}).get("export_id", "n/a"))
        if isinstance(comparison_bundle.get("export", {}), dict)
        else "n/a",
        "mismatch_reasons": [str(reason).strip() for reason in mismatch_reasons if str(reason).strip()],
        "candidate_spec": candidate_spec,
        "candidate_campaign": candidate_campaign,
        "comparison_bundle": comparison_bundle,
    }


def _benchmark_matrix_audit_payload(report: dict[str, Any] | Any) -> dict[str, Any]:
    payload = _benchmark_matrix_report_payload(report)
    entries = payload.get("entries", []) if isinstance(payload.get("entries", []), list) else []

    rows = [_benchmark_matrix_audit_candidate_payload(entry, rank=index) for index, entry in enumerate(entries, start=1)]
    rows.sort(
        key=lambda row: (
            0 if row.get("comparable") else 1,
            -float(row.get("quality_score_mean", 0.0) or 0.0),
            -float(row.get("confidence_level_mean", 0.0) or 0.0),
            str(row.get("candidate_label", "")),
            str(row.get("candidate_campaign_id", "")),
        )
    )
    for index, row in enumerate(rows, start=1):
        row["rank"] = index

    comparable_count = sum(1 for row in rows if row.get("comparable"))
    mismatch_count = len(rows) - comparable_count
    mismatch_reasons = sorted(
        {
            reason
            for row in rows
            for reason in row.get("mismatch_reasons", [])
            if isinstance(reason, str) and reason.strip()
        }
    )
    best_candidate = rows[0] if rows else None
    worst_candidate = rows[-1] if rows else None
    quality_scores = [float(row.get("quality_score_mean", 0.0) or 0.0) for row in rows]
    confidence_levels = [float(row.get("confidence_level_mean", 0.0) or 0.0) for row in rows]

    summary = {
        "matrix_id": payload.get("matrix_id", payload.get("benchmark_id")),
        "benchmark_id": payload.get("benchmark_id", payload.get("matrix_id")),
        "baseline_campaign_id": payload.get("baseline_campaign_id"),
        "candidate_count": len(rows),
        "candidate_labels": [str(row.get("candidate_label", "")).strip() for row in rows if str(row.get("candidate_label", "")).strip()],
        "candidate_campaign_ids": [
            str(row.get("candidate_campaign_id", "")).strip()
            for row in rows
            if str(row.get("candidate_campaign_id", "")).strip()
        ],
        "comparison_ids": [
            str(row.get("comparison_id", "")).strip()
            for row in rows
            if str(row.get("comparison_id", "")).strip()
        ],
        "comparable_count": comparable_count,
        "mismatch_count": mismatch_count,
        "comparable": mismatch_count == 0,
        "mismatch_reasons": mismatch_reasons,
        "runtime_values": list(payload.get("summary", {}).get("runtime_values", []))
        if isinstance(payload.get("summary", {}), dict)
        else [],
        "engine_values": list(payload.get("summary", {}).get("engine_values", []))
        if isinstance(payload.get("summary", {}), dict)
        else [],
        "quality_score_mean": (sum(quality_scores) / len(quality_scores)) if quality_scores else 0.0,
        "quality_score_min": min(quality_scores) if quality_scores else 0.0,
        "quality_score_max": max(quality_scores) if quality_scores else 0.0,
        "confidence_level_mean": (sum(confidence_levels) / len(confidence_levels)) if confidence_levels else 0.0,
        "confidence_level_min": min(confidence_levels) if confidence_levels else 0.0,
        "confidence_level_max": max(confidence_levels) if confidence_levels else 0.0,
        "best_candidate": best_candidate,
        "worst_candidate": worst_candidate,
        "top_candidates": rows[:3],
        "bottom_candidates": rows[-3:] if len(rows) > 3 else list(rows),
    }

    return {
        **payload,
        "benchmark_id": summary["benchmark_id"],
        "matrix_id": summary["matrix_id"],
        "candidate_count": summary["candidate_count"],
        "candidate_labels": summary["candidate_labels"],
        "candidate_campaign_ids": summary["candidate_campaign_ids"],
        "comparison_ids": summary["comparison_ids"],
        "leaderboard": rows,
        "best_candidate": best_candidate,
        "worst_candidate": worst_candidate,
        "summary": summary,
        "metadata": {
            **(payload.get("metadata", {}) if isinstance(payload.get("metadata", {}), dict) else {}),
            "artifact_kind": "matrix_benchmark_audit",
            "leaderboard_size": len(rows),
        },
    }


def _render_deliberation_campaign_benchmark_matrix_audit_markdown(
    report: dict[str, Any] | Any,
) -> str:
    audit = _benchmark_matrix_audit_payload(report)
    summary = audit.get("summary", {}) if isinstance(audit.get("summary", {}), dict) else {}
    leaderboard = audit.get("leaderboard", []) if isinstance(audit.get("leaderboard", []), list) else []
    best_candidate = audit.get("best_candidate", {}) if isinstance(audit.get("best_candidate", {}), dict) else {}
    worst_candidate = audit.get("worst_candidate", {}) if isinstance(audit.get("worst_candidate", {}), dict) else {}
    mismatch_reasons = ", ".join(summary.get("mismatch_reasons", [])) if summary.get("mismatch_reasons") else "none"
    lines = [
        "# Deliberation Campaign Matrix Benchmark Audit",
        f"- Benchmark ID: {audit.get('benchmark_id', 'n/a')}",
        f"- Matrix ID: {audit.get('matrix_id', 'n/a')}",
        f"- Created At: {audit.get('created_at', 'n/a')}",
        f"- Output Dir: {audit.get('output_dir', 'n/a')}",
        f"- Report Path: {audit.get('report_path', 'n/a')}",
        f"- Baseline Campaign ID: {summary.get('baseline_campaign_id', 'n/a')}",
        f"- Candidate Count: {summary.get('candidate_count', 0)}",
        f"- Comparable: {'yes' if summary.get('comparable') else 'no'}",
        f"- Mismatch Reasons: {mismatch_reasons}",
        f"- Best Candidate: {best_candidate.get('candidate_label', 'n/a')}",
        f"- Worst Candidate: {worst_candidate.get('candidate_label', 'n/a')}",
        "",
        "## Leaderboard",
        "| Rank | Candidate | Comparable | Quality | Confidence | Comparison ID | Export ID | Mismatch Reasons |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in leaderboard:
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("rank", "n/a")),
                    str(row.get("candidate_label", "n/a")),
                    "yes" if row.get("comparable") else "no",
                    f"{float(row.get('quality_score_mean', 0.0) or 0.0):.3f}",
                    f"{float(row.get('confidence_level_mean', 0.0) or 0.0):.3f}",
                    str(row.get("comparison_id", "n/a")),
                    str(row.get("export_id", "n/a")),
                    ", ".join(row.get("mismatch_reasons", [])) if row.get("mismatch_reasons") else "none",
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _print_deliberation_campaign_benchmark_matrix_audit(
    report: dict[str, Any] | Any,
    *,
    as_json: bool = False,
) -> None:
    payload = _benchmark_matrix_audit_payload(report)
    if as_json:
        _print_json(payload)
        return

    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    best_candidate = payload.get("best_candidate", {}) if isinstance(payload.get("best_candidate", {}), dict) else {}
    worst_candidate = payload.get("worst_candidate", {}) if isinstance(payload.get("worst_candidate", {}), dict) else {}
    console.print(
        Panel(
            f"[bold blue]Matrix ID:[/bold blue] {payload.get('matrix_id', 'n/a')}\n"
            f"[bold blue]Baseline Campaign:[/bold blue] {summary.get('baseline_campaign_id', 'n/a')}\n"
            f"[bold blue]Candidates:[/bold blue] {summary.get('candidate_count', 0)}\n"
            f"[bold blue]Comparable:[/bold blue] {'yes' if summary.get('comparable') else 'no'}\n"
            f"[bold blue]Best:[/bold blue] {best_candidate.get('candidate_label', 'n/a')}\n"
            f"[bold blue]Worst:[/bold blue] {worst_candidate.get('candidate_label', 'n/a')}\n"
            f"[bold blue]Report:[/bold blue] {payload.get('report_path', 'n/a')}\n"
            f"[bold blue]Output Dir:[/bold blue] {payload.get('output_dir', 'n/a')}"
        )
    )
    table = Table(title="Matrix Benchmark Audit Leaderboard", show_lines=False)
    table.add_column("Rank", style="cyan", no_wrap=True)
    table.add_column("Candidate", style="white")
    table.add_column("Comparable", style="green")
    table.add_column("Quality", style="yellow")
    table.add_column("Confidence", style="yellow")
    table.add_column("Comparison", style="cyan", no_wrap=True)
    table.add_column("Export", style="magenta")
    for row in payload.get("leaderboard", []) if isinstance(payload.get("leaderboard", []), list) else []:
        if not isinstance(row, dict):
            continue
        table.add_row(
            str(row.get("rank", "n/a")),
            str(row.get("candidate_label", "n/a")),
            "yes" if row.get("comparable") else "no",
            f"{float(row.get('quality_score_mean', 0.0) or 0.0):.3f}",
            f"{float(row.get('confidence_level_mean', 0.0) or 0.0):.3f}",
            str(row.get("comparison_id", "n/a")),
            str(row.get("export_id", "n/a")),
        )
    console.print(table)
    console.print(
        Panel(
            f"[bold blue]Top Candidate:[/bold blue] {best_candidate.get('candidate_label', 'n/a')}\n"
            f"[bold blue]Bottom Candidate:[/bold blue] {worst_candidate.get('candidate_label', 'n/a')}\n"
            f"[bold blue]Mismatch Reasons:[/bold blue] {', '.join(summary.get('mismatch_reasons', [])) or 'none'}"
        )
    )


def _load_deliberation_campaign_benchmark_matrix_audit(
    matrix_id: str,
    *,
    output_dir: str | Path | None = None,
    include_markdown: bool = True,
) -> dict[str, Any]:
    report = _load_deliberation_campaign_benchmark_matrix_report(matrix_id, output_dir=output_dir)
    payload = _benchmark_matrix_audit_payload(report)
    if include_markdown:
        payload["markdown"] = _render_deliberation_campaign_benchmark_matrix_audit_markdown(payload)
    return payload


def _matrix_benchmark_export_payload(export: dict[str, Any] | Any) -> dict[str, Any]:
    if hasattr(export, "model_dump"):
        payload = export.model_dump(mode="json")
    elif isinstance(export, dict):
        payload = dict(export)
    elif hasattr(export, "__dict__"):
        payload = dict(vars(export))
    else:
        payload = dict(export)
    created_at = payload.get("created_at")
    if isinstance(created_at, datetime):
        payload["created_at"] = created_at.isoformat()
    metadata = payload.get("metadata")
    if isinstance(metadata, dict) and metadata.get("matrix_id") is not None:
        payload.setdefault("matrix_id", metadata.get("matrix_id"))
    return payload


def _materialize_deliberation_campaign_benchmark_matrix_export(
    audit: dict[str, Any] | Any,
    *,
    format: str = "markdown",
    output_dir: str | Path | None = None,
    export_id: str | None = None,
) -> dict[str, Any]:
    normalized_format = str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        raise typer.BadParameter("format must be one of: markdown, json.")
    payload = _benchmark_matrix_audit_payload(audit)
    export_id = export_id or _benchmark_matrix_export_id(str(payload.get("matrix_id", payload.get("benchmark_id", "matrix"))), format=normalized_format)
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR)
    export_dir = _benchmark_matrix_export_dir(export_id, output_dir=base_dir)
    manifest_path = _benchmark_matrix_export_manifest_path(export_id, output_dir=base_dir)
    content_path = _benchmark_matrix_export_content_path(export_id, output_dir=base_dir, format=normalized_format)
    content = (
        _render_deliberation_campaign_benchmark_matrix_audit_markdown(payload)
        if normalized_format == "markdown"
        else json.dumps(payload, indent=2, sort_keys=True)
    )
    export = {
        "export_id": export_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(base_dir),
        "manifest_path": str(manifest_path),
        "content_path": str(content_path),
        "matrix_id": payload.get("matrix_id"),
        "benchmark_id": payload.get("benchmark_id"),
        "report_path": payload.get("report_path"),
        "format": normalized_format,
        "candidate_count": payload.get("candidate_count", 0),
        "candidate_labels": list(payload.get("candidate_labels", [])),
        "candidate_campaign_ids": list(payload.get("candidate_campaign_ids", [])),
        "comparison_ids": list(payload.get("comparison_ids", [])),
        "comparable": payload.get("summary", {}).get("comparable", False),
        "mismatch_reasons": list(payload.get("summary", {}).get("mismatch_reasons", [])),
        "best_candidate": payload.get("best_candidate"),
        "worst_candidate": payload.get("worst_candidate"),
        "content": content,
        "metadata": {
            **(payload.get("metadata", {}) if isinstance(payload.get("metadata", {}), dict) else {}),
            "manifest_path": str(manifest_path),
            "content_path": str(content_path),
            "persisted": True,
            "content_kind": "markdown" if normalized_format == "markdown" else "json",
            "content_format": normalized_format,
            "artifact_kind": "matrix_benchmark_export",
        },
    }
    export_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({key: value for key, value in export.items() if key != "content"}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    content_path.write_text(content, encoding="utf-8")
    return export


def _load_deliberation_campaign_benchmark_matrix_export(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
    include_content: bool = True,
) -> dict[str, Any]:
    manifest_path = _benchmark_matrix_export_manifest_path(export_id, output_dir=output_dir)
    helper = getattr(deliberation_campaign_core, "load_deliberation_campaign_matrix_benchmark_export", None)
    if callable(helper):
        try:
            export = helper(
                export_id,
                output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR,
                include_content=include_content,
            )
            payload = _matrix_benchmark_export_payload(export)
            if manifest_path.is_file():
                try:
                    raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    raw_manifest = None
                if isinstance(raw_manifest, dict):
                    payload = {**raw_manifest, **payload}
                    if include_content and payload.get("content") is None and raw_manifest.get("content_path"):
                        content_path = Path(str(raw_manifest["content_path"]))
                        if content_path.is_file():
                            payload["content"] = content_path.read_text(encoding="utf-8")
            payload.setdefault("matrix_id", payload.get("benchmark_id"))
            return payload
        except FileNotFoundError as exc:
            raise typer.BadParameter(
                f"No deliberation campaign benchmark matrix export found for {export_id!r}."
            ) from exc

    if not manifest_path.is_file():
        raise typer.BadParameter(f"No deliberation campaign benchmark matrix export found for {export_id!r}.")
    export = json.loads(manifest_path.read_text(encoding="utf-8"))
    if include_content and export.get("content_path"):
        content_path = Path(str(export["content_path"]))
        if content_path.is_file():
            export["content"] = content_path.read_text(encoding="utf-8")
    export.setdefault("matrix_id", export.get("benchmark_id"))
    return export


def _collect_deliberation_campaign_benchmark_matrix_exports(
    *,
    limit: int | None = None,
    output_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    helper = getattr(deliberation_campaign_core, "list_deliberation_campaign_matrix_benchmark_exports", None)
    if callable(helper):
        try:
            exports = helper(
                output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR,
                limit=limit,
            )
            return [_matrix_benchmark_export_payload(export) for export in exports]
        except Exception:
            pass

    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR)
    if not base_dir.exists():
        return []

    exports: list[dict[str, Any]] = []
    for export_dir in base_dir.iterdir():
        if not export_dir.is_dir():
            continue
        manifest_path = export_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            export = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(export, dict) and export:
            exports.append(export)

    exports.sort(
        key=lambda export: (
            str(export.get("created_at", "")),
            str(export.get("export_id", "")),
        ),
        reverse=True,
    )
    if limit is None:
        return exports
    return exports[: max(0, int(limit))]


def _load_deliberation_campaign_benchmark_matrix_exports(
    *,
    limit: int | None = None,
    output_dir: str | Path | None = None,
) -> list[dict[str, Any] | Any]:
    helper = getattr(deliberation_campaign_core, "list_deliberation_campaign_matrix_benchmark_exports", None)
    if callable(helper):
        try:
            exports = helper(limit=limit, output_dir=output_dir)
        except Exception:
            exports = None
        else:
            if isinstance(exports, list):
                return exports
    return _collect_deliberation_campaign_benchmark_matrix_exports(limit=limit, output_dir=output_dir)


def _load_deliberation_campaign_benchmark_matrix_comparison_exports(
    *,
    limit: int | None = None,
    output_dir: str | Path | None = None,
) -> list[dict[str, Any] | Any]:
    helper = getattr(
        deliberation_campaign_core,
        "list_deliberation_campaign_matrix_benchmark_comparison_exports",
        None,
    )
    if callable(helper):
        try:
            exports = helper(limit=limit, output_dir=output_dir)
        except Exception:
            exports = None
        else:
            if isinstance(exports, list):
                return exports
    return _collect_deliberation_campaign_benchmark_matrix_comparison_exports(limit=limit, output_dir=output_dir)


def _print_deliberation_campaign_benchmark_matrix_export(
    export: dict[str, Any] | Any,
    *,
    as_json: bool = False,
) -> None:
    payload = _matrix_benchmark_export_payload(export)
    if as_json:
        _print_json(payload)
        return

    console.print(
        Panel(
            f"[bold blue]Export ID:[/bold blue] {payload.get('export_id', 'n/a')}\n"
            f"[bold blue]Matrix ID:[/bold blue] {payload.get('matrix_id', payload.get('benchmark_id', 'n/a'))}\n"
            f"[bold blue]Format:[/bold blue] {payload.get('format', 'n/a')}\n"
            f"[bold blue]Manifest:[/bold blue] {payload.get('manifest_path', 'n/a')}\n"
            f"[bold blue]Content:[/bold blue] {payload.get('content_path', 'n/a')}"
        )
    )
    table = Table(title="Matrix Benchmark Export Summary", show_lines=False)
    table.add_column("Candidate Count", style="cyan", no_wrap=True)
    table.add_column("Comparable", style="green")
    table.add_column("Best Candidate", style="white")
    table.add_column("Worst Candidate", style="white")
    table.add_row(
        str(payload.get("candidate_count", 0)),
        "yes" if payload.get("comparable") else "no",
        str((payload.get("best_candidate") or {}).get("candidate_label", "n/a")),
        str((payload.get("worst_candidate") or {}).get("candidate_label", "n/a")),
    )
    console.print(table)


def _print_deliberation_campaign_benchmark_matrix_export_list(
    exports: list[dict[str, Any]],
    *,
    output_dir: str | Path | None = None,
    limit: int = 20,
    as_json: bool = False,
) -> None:
    payload = {
        "count": len(exports),
        "limit": limit,
        "output_dir": str(Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR)),
        "exports": exports,
    }
    if as_json:
        _print_json(payload)
        return

    console.print(
        Panel(
            f"[bold blue]Output Dir:[/bold blue] {payload['output_dir']}\n"
            f"[bold blue]Count:[/bold blue] {payload['count']} (limit={payload['limit']})"
        )
    )
    table = Table(title="Matrix Benchmark Exports", show_lines=False)
    table.add_column("Export ID", style="cyan", no_wrap=True)
    table.add_column("Matrix ID", style="white")
    table.add_column("Format", style="green")
    table.add_column("Created At", style="yellow")
    table.add_column("Content Path", style="magenta")
    for export in exports:
        table.add_row(
            str(export.get("export_id", "n/a")),
            str(export.get("matrix_id", export.get("benchmark_id", "n/a"))),
            str(export.get("format", "n/a")),
            str(export.get("created_at", "n/a")),
            _shorten_text(str(export.get("content_path", "n/a")), max_length=48),
    )
    console.print(table)


def _matrix_benchmark_export_comparison_report_payload(
    report: dict[str, Any] | Any,
) -> dict[str, Any]:
    if hasattr(report, "model_dump"):
        payload = report.model_dump(mode="json")
    elif isinstance(report, dict):
        payload = dict(report)
    elif hasattr(report, "__dict__"):
        payload = dict(vars(report))
    else:
        payload = dict(report)
    created_at = payload.get("created_at")
    if isinstance(created_at, datetime):
        payload["created_at"] = created_at.isoformat()
    return payload


def _matrix_benchmark_export_comparison_export_payload(
    export: dict[str, Any] | Any,
) -> dict[str, Any]:
    if hasattr(export, "model_dump"):
        payload = export.model_dump(mode="json")
    elif isinstance(export, dict):
        payload = dict(export)
    elif hasattr(export, "__dict__"):
        payload = dict(vars(export))
    else:
        payload = dict(export)
    created_at = payload.get("created_at")
    if isinstance(created_at, datetime):
        payload["created_at"] = created_at.isoformat()
    return payload


def _load_deliberation_campaign_benchmark_matrix_export_comparison_report(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    helper = getattr(
        deliberation_campaign_core,
        "load_deliberation_campaign_matrix_benchmark_export_comparison_report",
        None,
    )
    if not callable(helper):
        raise typer.BadParameter(
            "Matrix benchmark export comparison reports are not available in the current core."
        )
    try:
        return _matrix_benchmark_export_comparison_report_payload(
            helper(
                comparison_id,
                output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR,
            )
        )
    except FileNotFoundError as exc:
        raise typer.BadParameter(
            f"No deliberation campaign benchmark matrix export comparison found for {comparison_id!r}."
        ) from exc


def _collect_deliberation_campaign_benchmark_matrix_export_comparison_reports(
    *,
    limit: int | None = None,
    output_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    helper = getattr(
        deliberation_campaign_core,
        "list_deliberation_campaign_matrix_benchmark_export_comparison_reports",
        None,
    )
    if not callable(helper):
        return []
    reports = helper(
        output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR,
        limit=limit,
    )
    return [_matrix_benchmark_export_comparison_report_payload(report) for report in reports]


def _load_deliberation_campaign_benchmark_matrix_export_comparison_audit(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
    include_markdown: bool = True,
) -> dict[str, Any]:
    helper = getattr(
        deliberation_campaign_core,
        "load_deliberation_campaign_matrix_benchmark_export_comparison_audit",
        None,
    )
    if not callable(helper):
        raise typer.BadParameter(
            "Matrix benchmark export comparison audits are not available in the current core."
        )
    payload = helper(
        comparison_id,
        output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR,
        include_markdown=include_markdown,
    )
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    return dict(payload)


def _load_deliberation_campaign_benchmark_matrix_export_comparison_export(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    helper = getattr(
        deliberation_campaign_core,
        "load_deliberation_campaign_matrix_benchmark_export_comparison_export",
        None,
    )
    if not callable(helper):
        raise typer.BadParameter(
            "Matrix benchmark export comparison exports are not available in the current core."
        )
    try:
        return _matrix_benchmark_export_comparison_export_payload(
            helper(
                export_id,
                output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR,
                include_content=True,
            )
        )
    except FileNotFoundError as exc:
        raise typer.BadParameter(
            f"No deliberation campaign benchmark matrix export comparison export found for {export_id!r}."
        ) from exc


def _collect_deliberation_campaign_benchmark_matrix_export_comparison_exports(
    *,
    limit: int | None = None,
    output_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    helper = getattr(
        deliberation_campaign_core,
        "list_deliberation_campaign_matrix_benchmark_export_comparison_exports",
        None,
    )
    if not callable(helper):
        return []
    exports = helper(
        output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR,
        limit=limit,
    )
    return [_matrix_benchmark_export_comparison_export_payload(export) for export in exports]


def _print_deliberation_campaign_benchmark_matrix_export_comparison(
    comparison_report: dict[str, Any] | Any,
    *,
    as_json: bool = False,
) -> None:
    payload = _matrix_benchmark_export_comparison_report_payload(comparison_report)
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    entries = payload.get("entries", []) if isinstance(payload.get("entries", []), list) else []
    if as_json:
        _print_json(payload)
        return

    console.print(
        Panel(
            f"[bold blue]Comparison ID:[/bold blue] {payload.get('comparison_id', 'n/a')}\n"
            f"[bold blue]Export Count:[/bold blue] {summary.get('export_count', len(entries))}\n"
            f"[bold blue]Comparable:[/bold blue] {'yes' if summary.get('comparable') else 'no'}\n"
            f"[bold blue]Mismatch Reasons:[/bold blue] {', '.join(summary.get('mismatch_reasons', [])) or 'none'}\n"
            f"[bold blue]Report:[/bold blue] {payload.get('report_path', 'n/a')}"
        )
    )
    table = Table(title="Matrix Benchmark Export Comparison", show_lines=False)
    table.add_column("Export ID", style="cyan", no_wrap=True)
    table.add_column("Benchmark ID", style="white")
    table.add_column("Format", style="green")
    table.add_column("Comparable", style="yellow")
    table.add_column("Score", style="magenta")
    table.add_column("Confidence", style="magenta")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        table.add_row(
            str(entry.get("export_id", "n/a")),
            str(entry.get("benchmark_id", "n/a")),
            str(entry.get("format", "n/a")),
            "yes" if entry.get("comparable") else "no",
            f"{float(entry.get('quality_score_mean', 0.0) or 0.0):.3f}",
            f"{float(entry.get('confidence_level_mean', 0.0) or 0.0):.3f}",
        )
    console.print(table)


def _print_deliberation_campaign_benchmark_matrix_export_comparison_list(
    reports: list[dict[str, Any]],
    *,
    output_dir: str | Path | None = None,
    limit: int = 20,
    as_json: bool = False,
) -> None:
    payload = {
        "count": len(reports),
        "limit": limit,
        "output_dir": str(
            Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR)
        ),
        "comparisons": reports,
    }
    if as_json:
        _print_json(payload)
        return

    console.print(
        Panel(
            f"[bold blue]Output Dir:[/bold blue] {payload['output_dir']}\n"
            f"[bold blue]Count:[/bold blue] {payload['count']} (limit={payload['limit']})"
        )
    )
    table = Table(title="Matrix Benchmark Export Comparisons", show_lines=False)
    table.add_column("Comparison ID", style="cyan", no_wrap=True)
    table.add_column("Created At", style="yellow")
    table.add_column("Exports", style="white")
    table.add_column("Comparable", style="green")
    table.add_column("Report", style="magenta")
    for report in reports:
        summary = report.get("summary", {}) if isinstance(report.get("summary", {}), dict) else {}
        table.add_row(
            str(report.get("comparison_id", "n/a")),
            str(report.get("created_at", "n/a")),
            str(summary.get("export_count", len(summary.get("export_ids", [])))),
            "yes" if summary.get("comparable") else "no",
            _shorten_text(str(report.get("report_path", "n/a")), max_length=48),
        )
    console.print(table)


def _print_deliberation_campaign_benchmark_matrix_export_comparison_audit(
    audit: dict[str, Any] | Any,
    *,
    as_json: bool = False,
) -> None:
    payload = (
        audit.model_dump(mode="json")
        if hasattr(audit, "model_dump")
        else dict(audit)
    )
    if as_json:
        _print_json(payload)
        return
    console.print(
        Panel(
            f"[bold blue]Comparison ID:[/bold blue] {payload.get('comparison_id', 'n/a')}\n"
            f"[bold blue]Comparable:[/bold blue] {'yes' if payload.get('comparable') else 'no'}\n"
            f"[bold blue]Mismatch Reasons:[/bold blue] {', '.join(payload.get('mismatch_reasons', [])) or 'none'}\n"
            f"[bold blue]Report:[/bold blue] {payload.get('report_path', 'n/a')}"
        )
    )
    markdown = payload.get("markdown")
    if isinstance(markdown, str) and markdown.strip():
        console.print(markdown)


def _print_deliberation_campaign_benchmark_matrix_export_comparison_export(
    export: dict[str, Any] | Any,
    *,
    as_json: bool = False,
) -> None:
    payload = _matrix_benchmark_export_comparison_export_payload(export)
    if as_json:
        _print_json(payload)
        return
    console.print(
        Panel(
            f"[bold blue]Export ID:[/bold blue] {payload.get('export_id', 'n/a')}\n"
            f"[bold blue]Comparison ID:[/bold blue] {payload.get('comparison_id', 'n/a')}\n"
            f"[bold blue]Format:[/bold blue] {payload.get('format', 'n/a')}\n"
            f"[bold blue]Manifest:[/bold blue] {payload.get('manifest_path', 'n/a')}\n"
            f"[bold blue]Content:[/bold blue] {payload.get('content_path', 'n/a')}"
        )
    )


def _print_deliberation_campaign_benchmark_matrix_export_comparison_export_list(
    exports: list[dict[str, Any]],
    *,
    output_dir: str | Path | None = None,
    limit: int = 20,
    as_json: bool = False,
) -> None:
    payload = {
        "count": len(exports),
        "limit": limit,
        "output_dir": str(
            Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR)
        ),
        "exports": exports,
    }
    if as_json:
        _print_json(payload)
        return

    console.print(
        Panel(
            f"[bold blue]Output Dir:[/bold blue] {payload['output_dir']}\n"
            f"[bold blue]Count:[/bold blue] {payload['count']} (limit={payload['limit']})"
        )
    )
    table = Table(title="Matrix Benchmark Export Comparison Exports", show_lines=False)
    table.add_column("Export ID", style="cyan", no_wrap=True)
    table.add_column("Comparison ID", style="white")
    table.add_column("Format", style="green")
    table.add_column("Created At", style="yellow")
    table.add_column("Content Path", style="magenta")
    for export in exports:
        table.add_row(
            str(export.get("export_id", "n/a")),
            str(export.get("comparison_id", "n/a")),
            str(export.get("format", "n/a")),
            str(export.get("created_at", "n/a")),
            _shorten_text(str(export.get("content_path", "n/a")), max_length=48),
        )
    console.print(table)


def _print_deliberation_campaign_benchmark_matrix_list(
    reports: list[DeliberationCampaignMatrixBenchmarkBundle | dict[str, Any]],
    *,
    output_dir: str | Path | None = None,
    limit: int = 20,
    as_json: bool = False,
) -> None:
    payload = {
        "count": len(reports),
        "limit": limit,
        "output_dir": str(Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR)),
        "matrices": [_benchmark_matrix_report_payload(report) for report in reports],
    }
    if as_json:
        _print_json(payload)
        return

    console.print(
        Panel(
            f"[bold blue]Output Dir:[/bold blue] {payload['output_dir']}\n"
            f"[bold blue]Count:[/bold blue] {payload['count']} (limit={payload['limit']})"
        )
    )
    table = Table(title="Deliberation Campaign Benchmark Matrices", show_lines=False)
    table.add_column("Matrix ID", style="cyan", no_wrap=True)
    table.add_column("Created At", style="magenta")
    table.add_column("Baseline", style="white")
    table.add_column("Candidates", style="white")
    table.add_column("Comparable", style="green")
    table.add_column("Report", style="yellow")
    for matrix in payload["matrices"]:
        summary = matrix.get("summary", {}) if isinstance(matrix.get("summary", {}), dict) else {}
        candidate_ids = summary.get("candidate_campaign_ids", []) if isinstance(summary.get("candidate_campaign_ids", []), list) else []
        candidate_text = ", ".join(candidate_ids) if candidate_ids else str(summary.get("candidate_count", 0))
        table.add_row(
            str(matrix.get("matrix_id", matrix.get("benchmark_id", "n/a"))),
            str(matrix.get("created_at", "n/a")),
            str(matrix.get("baseline_campaign_id", matrix.get("baseline_campaign", {}).get("campaign_id", "n/a"))),
            _shorten_text(candidate_text, max_length=36),
            "yes" if summary.get("mismatch_count", 0) == 0 else "no",
            str(matrix.get("report_path", "n/a")),
        )
    console.print(table)


def _matrix_candidate_specs(
    *,
    candidate_runtimes: list[RuntimeBackend] | None,
    candidate_engine_preferences: list[EnginePreference] | None,
    candidate_campaign_ids: list[str] | None,
) -> list[DeliberationCampaignMatrixCandidateSpec]:
    runtimes = list(candidate_runtimes or [])
    engines = list(candidate_engine_preferences or [])
    campaign_ids = [str(candidate_id).strip() for candidate_id in (candidate_campaign_ids or []) if str(candidate_id).strip()]

    if not runtimes:
        runtimes = [RuntimeBackend.legacy]
    if not engines:
        engines = [EnginePreference.oasis]

    specs: list[DeliberationCampaignMatrixCandidateSpec] = []
    candidate_count = len(runtimes) * len(engines)
    if campaign_ids and len(campaign_ids) != candidate_count:
        raise typer.BadParameter("candidate campaign IDs must be provided once per runtime x engine matrix cell.")

    for index, (runtime, engine_preference) in enumerate(
        ((runtime, engine) for runtime in runtimes for engine in engines),
        start=1,
    ):
        runtime_value = runtime.value if hasattr(runtime, "value") else str(runtime)
        engine_value = engine_preference.value if hasattr(engine_preference, "value") else str(engine_preference)
        campaign_id = (
            campaign_ids[index - 1]
            if campaign_ids
            else f"matrix_candidate__{runtime_value}__{engine_value}"
        )
        specs.append(
            DeliberationCampaignMatrixCandidateSpec(
                label=f"{runtime_value}__{engine_value}",
                campaign_id=campaign_id,
                runtime=runtime_value,
                engine_preference=engine_preference,
            )
        )
    return specs


def _run_deliberation_campaign_benchmark_matrix(
    *,
    topic: str,
    objective: str | None,
    mode: DeliberationMode,
    participants: list[str],
    documents: list[str],
    entities: list[Any],
    interventions: list[str],
    max_agents: int,
    population_size: int | None,
    rounds: int,
    time_horizon: str,
    config_path: str,
    benchmark_path: str,
    sample_count: int,
    stability_runs: int,
    baseline_runtime: RuntimeBackend,
    candidate_runtimes: list[RuntimeBackend],
    allow_fallback: bool,
    baseline_engine_preference: EnginePreference,
    candidate_engine_preferences: list[EnginePreference],
    budget_max: float,
    timeout_seconds: int,
    backend_mode: str | None,
    campaign_output_dir: str | Path,
    comparison_output_dir: str | Path,
    export_output_dir: str | Path,
    benchmark_output_dir: str | Path | None,
    format: str,
    baseline_campaign_id: str | None = None,
    candidate_campaign_ids: list[str] | None = None,
    matrix_id: str | None = None,
) -> dict[str, Any]:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        raise typer.BadParameter("format must be one of: markdown, json.")
    candidate_specs = _matrix_candidate_specs(
        candidate_runtimes=candidate_runtimes,
        candidate_engine_preferences=candidate_engine_preferences,
        candidate_campaign_ids=candidate_campaign_ids,
    )
    helper = getattr(deliberation_campaign_core, "run_deliberation_campaign_matrix_benchmark_sync", None)
    if not callable(helper):
        raise typer.BadParameter("The campaign matrix benchmark helper is unavailable in this build.")

    bundle_result = helper(
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
        ensemble_engines=None,
        budget_max=budget_max,
        timeout_seconds=timeout_seconds,
        benchmark_path=benchmark_path,
        config_path=config_path,
        backend_mode=backend_mode,
        persist=True,
        output_dir=campaign_output_dir,
        comparison_output_dir=comparison_output_dir,
        export_output_dir=export_output_dir,
        benchmark_output_dir=benchmark_output_dir,
        format=normalized_format,
        benchmark_id=matrix_id,
        baseline_campaign_id=baseline_campaign_id,
        client=None,
        runner=None,
    )
    return _benchmark_matrix_report_payload(bundle_result)


def _deliberation_campaign_index_payload(
    *,
    limit: int = 10,
    campaign_output_dir: str | Path | None = None,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
    benchmark_output_dir: str | Path | None = None,
    matrix_benchmark_output_dir: str | Path | None = None,
    matrix_benchmark_export_output_dir: str | Path | None = None,
    matrix_benchmark_comparison_output_dir: str | Path | None = None,
    matrix_benchmark_comparison_export_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    helper = getattr(deliberation_campaign_core, "build_deliberation_campaign_artifact_index", None)
    if callable(helper):
        try:
            payload = helper(
                limit=limit,
                campaign_output_dir=campaign_output_dir,
                comparison_output_dir=comparison_output_dir,
                export_output_dir=export_output_dir,
                benchmark_output_dir=benchmark_output_dir,
                matrix_benchmark_output_dir=matrix_benchmark_output_dir,
                matrix_benchmark_export_output_dir=matrix_benchmark_export_output_dir,
                matrix_benchmark_comparison_output_dir=matrix_benchmark_comparison_output_dir,
                matrix_benchmark_comparison_export_output_dir=matrix_benchmark_comparison_export_output_dir,
            )
            if hasattr(payload, "model_dump"):
                payload = payload.model_dump(mode="json")
            else:
                payload = dict(payload)
            if isinstance(payload, dict):
                recent = payload.get("recent", {}) if isinstance(payload.get("recent", {}), dict) else {}
                counts = payload.get("counts", {}) if isinstance(payload.get("counts", {}), dict) else {}
                output_dirs = payload.get("output_dirs", {}) if isinstance(payload.get("output_dirs", {}), dict) else {}
                matrix_benchmark_exports = _load_deliberation_campaign_benchmark_matrix_exports(
                    limit=limit,
                    output_dir=matrix_benchmark_export_output_dir,
                )
                matrix_benchmark_comparison_exports = _load_deliberation_campaign_benchmark_matrix_comparison_exports(
                    limit=limit,
                    output_dir=matrix_benchmark_comparison_export_output_dir,
                )
                if matrix_benchmark_exports and not recent.get("matrix_benchmark_exports"):
                    recent = dict(recent)
                    recent["matrix_benchmark_exports"] = [
                        _matrix_benchmark_export_payload(report) for report in matrix_benchmark_exports
                    ]
                if matrix_benchmark_comparison_exports and not recent.get("matrix_benchmark_comparison_exports"):
                    recent = dict(recent)
                    recent["matrix_benchmark_comparison_exports"] = [
                        _matrix_benchmark_comparison_export_payload(report)
                        for report in matrix_benchmark_comparison_exports
                    ]
                if matrix_benchmark_exports or matrix_benchmark_comparison_exports:
                    counts = dict(counts)
                    counts["matrix_benchmark_exports"] = max(
                        int(counts.get("matrix_benchmark_exports", 0) or 0),
                        len(matrix_benchmark_exports),
                    )
                    counts["matrix_benchmark_comparison_exports"] = max(
                        int(counts.get("matrix_benchmark_comparison_exports", 0) or 0),
                        len(matrix_benchmark_comparison_exports),
                    )
                    output_dirs = dict(output_dirs)
                    output_dirs.setdefault(
                        "matrix_benchmark_exports",
                        str(
                            Path(
                                matrix_benchmark_export_output_dir
                                or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR
                            )
                        ),
                    )
                    output_dirs.setdefault(
                        "matrix_benchmark_comparison_exports",
                        str(
                            Path(
                                matrix_benchmark_comparison_export_output_dir
                                or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR
                            )
                        ),
                    )
                    payload["recent"] = recent
                    payload["counts"] = counts
                    payload["output_dirs"] = output_dirs
            return payload
        except Exception:
            pass

    campaigns = _collect_deliberation_campaign_reports(limit=limit, output_dir=campaign_output_dir)
    comparisons = _collect_deliberation_campaign_comparison_reports(limit=limit, output_dir=comparison_output_dir)
    exports = _collect_deliberation_campaign_comparison_exports(limit=limit, output_dir=export_output_dir)
    benchmarks = _collect_deliberation_campaign_benchmark_reports(limit=limit, output_dir=benchmark_output_dir)
    matrix_benchmarks = _collect_deliberation_campaign_benchmark_matrix_reports(
        limit=limit,
        output_dir=matrix_benchmark_output_dir,
    )
    matrix_benchmark_exports = _load_deliberation_campaign_benchmark_matrix_exports(
        limit=limit,
        output_dir=matrix_benchmark_export_output_dir,
    )
    matrix_benchmark_comparisons = _collect_deliberation_campaign_benchmark_matrix_comparison_reports(
        limit=limit,
        output_dir=matrix_benchmark_comparison_output_dir,
    )
    matrix_benchmark_comparison_exports = _load_deliberation_campaign_benchmark_matrix_comparison_exports(
        limit=limit,
        output_dir=matrix_benchmark_comparison_export_output_dir,
    )
    return {
        "ok": True,
        "limit": limit,
        "output_dirs": {
            "campaigns": str(Path(campaign_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR)),
            "comparisons": str(Path(comparison_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR)),
            "exports": str(Path(export_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR)),
            "benchmarks": str(Path(benchmark_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR)),
            "matrix_benchmarks": str(Path(matrix_benchmark_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR)),
            "matrix_benchmark_exports": str(
                Path(matrix_benchmark_export_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR)
            ),
            "matrix_benchmark_comparisons": str(
                Path(
                    matrix_benchmark_comparison_output_dir
                    or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR
                )
            ),
            "matrix_benchmark_comparison_exports": str(
                Path(
                    matrix_benchmark_comparison_export_output_dir
                    or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR
                )
            ),
        },
        "counts": {
            "campaigns": len(campaigns),
            "comparisons": len(comparisons),
            "exports": len(exports),
            "benchmarks": len(benchmarks),
            "matrix_benchmarks": len(matrix_benchmarks),
            "matrix_benchmark_exports": len(matrix_benchmark_exports),
            "matrix_benchmark_comparisons": len(matrix_benchmark_comparisons),
            "matrix_benchmark_comparison_exports": len(matrix_benchmark_comparison_exports),
        },
        "recent": {
            "campaigns": [_campaign_list_payload(report) for report in campaigns],
            "comparisons": [_comparison_list_payload(report) for report in comparisons],
            "exports": [_comparison_export_payload(report) for report in exports],
            "benchmarks": [_benchmark_report_payload(report) for report in benchmarks],
            "matrix_benchmarks": [_benchmark_matrix_report_payload(report) for report in matrix_benchmarks],
            "matrix_benchmark_exports": [_matrix_benchmark_export_payload(report) for report in matrix_benchmark_exports],
            "matrix_benchmark_comparisons": [
                _matrix_benchmark_comparison_report_payload(report)
                for report in matrix_benchmark_comparisons
            ],
            "matrix_benchmark_comparison_exports": [
                _matrix_benchmark_comparison_export_payload(report)
                for report in matrix_benchmark_comparison_exports
            ],
        },
    }


def _dashboard_item_kind(item: dict[str, Any]) -> str:
    if item.get("artifact_kind") == "matrix_benchmark_comparison_export":
        return "matrix_benchmark_comparison_export"
    if item.get("artifact_kind") == "matrix_benchmark_comparison":
        return "matrix_benchmark_comparison"
    if item.get("artifact_kind") == "matrix_benchmark_export":
        return "matrix_benchmark_export"
    if "campaign_id" in item:
        return "campaign"
    if "comparison_id" in item and "export_id" not in item:
        return "comparison"
    if "export_id" in item and "benchmark_id" not in item:
        return "export"
    if "benchmark_id" in item and (
        item.get("artifact_kind") == "matrix_benchmark"
        or "candidate_count" in item
        or "candidate_labels" in item
        or "mismatch_count" in item
    ):
        return "matrix_benchmark"
    if "benchmark_id" in item:
        return "benchmark"
    return "artifact"


def _dashboard_rows_from_index(index_payload: dict[str, Any]) -> list[dict[str, Any]]:
    recent = index_payload.get("recent", {}) if isinstance(index_payload.get("recent", {}), dict) else {}
    rows: list[dict[str, Any]] = []

    for campaign in recent.get("campaigns", []) if isinstance(recent.get("campaigns", []), list) else []:
        summary = campaign.get("summary", {}) if isinstance(campaign.get("summary", {}), dict) else {}
        rows.append(
            {
                "artifact_kind": "campaign",
                "artifact_id": campaign.get("campaign_id"),
                "created_at": campaign.get("created_at"),
                "status": campaign.get("status"),
                "comparable": True,
                "quality_score_mean": summary.get("quality_score_mean"),
                "confidence_level_mean": summary.get("confidence_level_mean"),
                "runtime_summary": summary.get("runtime_counts") or campaign.get("runtime_requested"),
                "engine_summary": summary.get("engine_counts") or campaign.get("engine_requested"),
                "artifact_path": campaign.get("report_path"),
                "output_dir": campaign.get("output_dir"),
                "comparison_key": campaign.get("comparison_key")
                or campaign.get("metadata", {}).get("comparison_key")
                if isinstance(campaign.get("metadata", {}), dict)
                else None,
            }
        )

    for comparison in recent.get("comparisons", []) if isinstance(recent.get("comparisons", []), list) else []:
        summary = comparison.get("summary", {}) if isinstance(comparison.get("summary", {}), dict) else {}
        rows.append(
            {
                "artifact_kind": "comparison",
                "artifact_id": comparison.get("comparison_id"),
                "created_at": comparison.get("created_at"),
                "status": "comparison",
                "comparable": summary.get("comparable"),
                "quality_score_mean": summary.get("quality_score_mean"),
                "confidence_level_mean": summary.get("confidence_level_mean"),
                "runtime_summary": summary.get("runtime_values"),
                "engine_summary": summary.get("engine_values"),
                "artifact_path": comparison.get("report_path") or comparison.get("metadata", {}).get("report_path"),
                "output_dir": comparison.get("output_dir"),
                "comparison_key": comparison.get("comparison_key")
                or comparison.get("metadata", {}).get("comparison_key")
                if isinstance(comparison.get("metadata", {}), dict)
                else None,
            }
        )

    for export in recent.get("exports", []) if isinstance(recent.get("exports", []), list) else []:
        rows.append(
            {
                "artifact_kind": "export",
                "artifact_id": export.get("export_id"),
                "created_at": export.get("created_at"),
                "status": export.get("format"),
                "comparable": export.get("comparable"),
                "quality_score_mean": None,
                "confidence_level_mean": None,
                "runtime_summary": None,
                "engine_summary": None,
                "artifact_path": export.get("content_path") or export.get("manifest_path"),
                "output_dir": export.get("output_dir"),
                "comparison_key": None,
            }
        )

    for benchmark in recent.get("benchmarks", []) if isinstance(recent.get("benchmarks", []), list) else []:
        comparison_bundle = benchmark.get("comparison_bundle", {}) if isinstance(benchmark.get("comparison_bundle", {}), dict) else {}
        comparison_report = comparison_bundle.get("comparison_report", {}) if isinstance(comparison_bundle.get("comparison_report", {}), dict) else {}
        comparison_summary = comparison_report.get("summary", {}) if isinstance(comparison_report.get("summary", {}), dict) else {}
        rows.append(
            {
                "artifact_kind": "benchmark",
                "artifact_id": benchmark.get("benchmark_id"),
                "created_at": benchmark.get("created_at"),
                "status": "benchmark",
                "comparable": comparison_summary.get("comparable", benchmark.get("comparison", {}).get("comparable", True)),
                "quality_score_mean": comparison_summary.get("quality_score_mean"),
                "confidence_level_mean": comparison_summary.get("confidence_level_mean"),
                "runtime_summary": {
                    "baseline": benchmark.get("baseline_runtime"),
                    "candidate": benchmark.get("candidate_runtime"),
                },
                "engine_summary": {
                    "baseline": benchmark.get("baseline_engine_preference"),
                    "candidate": benchmark.get("candidate_engine_preference"),
                },
                "artifact_path": benchmark.get("report_path"),
                "output_dir": benchmark.get("output_dir"),
                "comparison_key": comparison_summary.get("comparison_key_values", [None])[0]
                if isinstance(comparison_summary.get("comparison_key_values", []), list) and comparison_summary.get("comparison_key_values")
                else benchmark.get("comparison_key"),
            }
        )

    for matrix_benchmark in recent.get("matrix_benchmarks", []) if isinstance(recent.get("matrix_benchmarks", []), list) else []:
        summary = matrix_benchmark.get("summary", {}) if isinstance(matrix_benchmark.get("summary", {}), dict) else {}
        baseline_campaign = (
            matrix_benchmark.get("baseline_campaign", {})
            if isinstance(matrix_benchmark.get("baseline_campaign", {}), dict)
            else {}
        )
        rows.append(
            {
                "artifact_kind": "matrix_benchmark",
                "artifact_id": matrix_benchmark.get("matrix_id", matrix_benchmark.get("benchmark_id")),
                "created_at": matrix_benchmark.get("created_at"),
                "status": "comparable" if summary.get("mismatch_count", 0) == 0 else "mismatch",
                "comparable": summary.get("mismatch_count", 0) == 0,
                "quality_score_mean": summary.get("quality_score_mean"),
                "confidence_level_mean": summary.get("confidence_level_mean"),
                "runtime_summary": _dashboard_sequence_summary(summary.get("runtime_values", []))
                if isinstance(summary.get("runtime_values", []), list)
                else str(summary.get("runtime_values") or "n/a"),
                "engine_summary": _dashboard_sequence_summary(summary.get("engine_values", []))
                if isinstance(summary.get("engine_values", []), list)
                else str(summary.get("engine_values") or "n/a"),
                "artifact_path": matrix_benchmark.get("report_path"),
                "output_dir": matrix_benchmark.get("output_dir"),
                "comparison_key": matrix_benchmark.get("benchmark_id"),
                "metadata": {
                    "baseline_campaign_id": matrix_benchmark.get("baseline_campaign_id", baseline_campaign.get("campaign_id")),
                    "candidate_count": summary.get("candidate_count"),
                    "candidate_campaign_ids": summary.get("candidate_campaign_ids", []),
                    "candidate_labels": summary.get("candidate_labels", []),
                    "comparison_ids": summary.get("comparison_ids", []),
                    "mismatch_count": summary.get("mismatch_count"),
                    "comparable_count": summary.get("comparable_count"),
                },
            }
        )

    for matrix_export in (
        recent.get("matrix_benchmark_exports", [])
        if isinstance(recent.get("matrix_benchmark_exports", []), list)
        else []
    ):
        rows.append(
            {
                "artifact_kind": "matrix_benchmark_export",
                "artifact_id": matrix_export.get("export_id"),
                "created_at": matrix_export.get("created_at"),
                "status": matrix_export.get("format"),
                "comparable": matrix_export.get("comparable"),
                "quality_score_mean": matrix_export.get("quality_score_mean"),
                "confidence_level_mean": matrix_export.get("confidence_level_mean"),
                "runtime_summary": None,
                "engine_summary": None,
                "artifact_path": matrix_export.get("content_path") or matrix_export.get("manifest_path"),
                "output_dir": matrix_export.get("output_dir"),
                "comparison_key": None,
                "metadata": {
                    "benchmark_id": matrix_export.get("benchmark_id"),
                    "benchmark_report_path": matrix_export.get("benchmark_report_path"),
                    "candidate_count": matrix_export.get("candidate_count"),
                    "candidate_labels": matrix_export.get("candidate_labels", []),
                    "candidate_campaign_ids": matrix_export.get("candidate_campaign_ids", []),
                    "comparison_ids": matrix_export.get("comparison_ids", []),
                    "comparable_count": matrix_export.get("comparable_count"),
                    "mismatch_count": matrix_export.get("mismatch_count"),
                    "best_candidate_label": matrix_export.get("best_candidate_label"),
                    "worst_candidate_label": matrix_export.get("worst_candidate_label"),
                },
            }
        )

    for matrix_comparison in (
        recent.get("matrix_benchmark_comparisons", [])
        if isinstance(recent.get("matrix_benchmark_comparisons", []), list)
        else []
    ):
        summary = (
            matrix_comparison.get("summary", {})
            if isinstance(matrix_comparison.get("summary", {}), dict)
            else {}
        )
        left_payload = (
            matrix_comparison.get("left", {})
            if isinstance(matrix_comparison.get("left", {}), dict)
            else {}
        )
        right_payload = (
            matrix_comparison.get("right", {})
            if isinstance(matrix_comparison.get("right", {}), dict)
            else {}
        )
        rows.append(
            {
                "artifact_kind": "matrix_benchmark_comparison",
                "artifact_id": matrix_comparison.get("comparison_id"),
                "created_at": matrix_comparison.get("created_at"),
                "status": "comparable" if summary.get("comparable") else "mismatch",
                "comparable": summary.get("comparable"),
                "quality_score_mean": None,
                "confidence_level_mean": None,
                "runtime_summary": summary.get("runtime_values"),
                "engine_summary": summary.get("engine_values"),
                "artifact_path": matrix_comparison.get("report_path"),
                "output_dir": matrix_comparison.get("output_dir"),
                "comparison_key": summary.get("candidate_structure_key_values"),
                "metadata": {
                    "left_matrix_id": left_payload.get("matrix_id", left_payload.get("benchmark_id")),
                    "right_matrix_id": right_payload.get("matrix_id", right_payload.get("benchmark_id")),
                    "mismatch_reasons": summary.get("mismatch_reasons", []),
                },
            }
        )

    for matrix_export in (
        recent.get("matrix_benchmark_comparison_exports", [])
        if isinstance(recent.get("matrix_benchmark_comparison_exports", []), list)
        else []
    ):
        rows.append(
            {
                "artifact_kind": "matrix_benchmark_comparison_export",
                "artifact_id": matrix_export.get("export_id"),
                "created_at": matrix_export.get("created_at"),
                "status": matrix_export.get("format"),
                "comparable": matrix_export.get("comparable"),
                "quality_score_mean": None,
                "confidence_level_mean": None,
                "runtime_summary": None,
                "engine_summary": None,
                "artifact_path": matrix_export.get("content_path") or matrix_export.get("manifest_path"),
                "output_dir": matrix_export.get("output_dir"),
                "comparison_key": None,
                "metadata": {
                    "comparison_id": matrix_export.get("comparison_id"),
                    "mismatch_reasons": matrix_export.get("mismatch_reasons", []),
                },
            }
        )

    return rows


def _deliberation_campaign_dashboard_payload(
    *,
    kinds: list[str] | None = None,
    limit: int = 10,
    sort_by: str = "created_at",
    campaign_status: DeliberationCampaignStatus | str | None = None,
    comparable_only: bool = False,
    campaign_output_dir: str | Path | None = None,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
    benchmark_output_dir: str | Path | None = None,
    matrix_benchmark_output_dir: str | Path | None = None,
    matrix_benchmark_export_output_dir: str | Path | None = None,
    matrix_benchmark_comparison_output_dir: str | Path | None = None,
    matrix_benchmark_comparison_export_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    helper = getattr(deliberation_campaign_core, "build_deliberation_campaign_dashboard", None)
    if callable(helper):
        try:
            dashboard = helper(
                kinds=kinds,
                limit=limit,
                sort_by=sort_by,
                campaign_status=campaign_status,
                comparable_only=comparable_only,
                campaign_output_dir=campaign_output_dir,
                comparison_output_dir=comparison_output_dir,
                export_output_dir=export_output_dir,
                benchmark_output_dir=benchmark_output_dir,
                matrix_benchmark_output_dir=matrix_benchmark_output_dir,
                matrix_benchmark_export_output_dir=matrix_benchmark_export_output_dir,
                matrix_benchmark_comparison_output_dir=matrix_benchmark_comparison_output_dir,
                matrix_benchmark_comparison_export_output_dir=matrix_benchmark_comparison_export_output_dir,
            )
            if hasattr(dashboard, "model_dump"):
                return dashboard.model_dump(mode="json")
            return dict(dashboard)
        except Exception:
            pass

    index_payload = _deliberation_campaign_index_payload(
        limit=max(limit, 1),
        campaign_output_dir=campaign_output_dir,
        comparison_output_dir=comparison_output_dir,
        export_output_dir=export_output_dir,
        benchmark_output_dir=benchmark_output_dir,
        matrix_benchmark_output_dir=matrix_benchmark_output_dir,
        matrix_benchmark_export_output_dir=matrix_benchmark_export_output_dir,
        matrix_benchmark_comparison_output_dir=matrix_benchmark_comparison_output_dir,
        matrix_benchmark_comparison_export_output_dir=matrix_benchmark_comparison_export_output_dir,
    )
    rows = _dashboard_rows_from_index(index_payload)
    selected_kinds: list[str] = []
    for kind in kinds or []:
        normalized_kind = str(kind).strip().lower()
        if normalized_kind and normalized_kind not in selected_kinds:
            selected_kinds.append(normalized_kind)
    selected_kind_set = set(selected_kinds)
    if selected_kind_set:
        rows = [row for row in rows if row.get("artifact_kind") in selected_kind_set]
    selected_status = None if campaign_status is None else str(getattr(campaign_status, "value", campaign_status))
    if selected_status:
        rows = [row for row in rows if not (row.get("artifact_kind") == "campaign" and str(row.get("status")) != selected_status)]
    if comparable_only:
        rows = [row for row in rows if row.get("comparable") is True]

    sort_key = str(sort_by).strip().lower() or "created_at"
    if sort_key == "kind":
        rows.sort(key=lambda row: (row.get("artifact_kind") or "", row.get("created_at") or "", row.get("artifact_id") or ""))
    elif sort_key == "status":
        rows.sort(key=lambda row: (str(row.get("status") or ""), row.get("created_at") or "", row.get("artifact_id") or ""))
    elif sort_key == "comparable":
        rows.sort(key=lambda row: (row.get("comparable") is not True, row.get("created_at") or "", row.get("artifact_id") or ""))
    else:
        rows.sort(key=lambda row: (row.get("created_at") or "", row.get("artifact_kind") or "", row.get("artifact_id") or ""), reverse=True)

    rows = rows[: max(0, int(limit))]
    return {
        "ok": True,
        "limit": limit,
        "sort_by": sort_key,
        "kinds": selected_kinds
        if selected_kinds
        else [
            "campaign",
            "comparison",
            "export",
            "benchmark",
            "matrix_benchmark",
            "matrix_benchmark_export",
            "matrix_benchmark_comparison",
            "matrix_benchmark_comparison_export",
        ],
        "campaign_status": None if selected_status is None else selected_status,
        "comparable_only": comparable_only,
        "counts": {
            "total": len(rows),
            "campaigns": sum(1 for row in rows if row["artifact_kind"] == "campaign"),
            "comparisons": sum(1 for row in rows if row["artifact_kind"] == "comparison"),
            "exports": sum(1 for row in rows if row["artifact_kind"] == "export"),
            "benchmarks": sum(1 for row in rows if row["artifact_kind"] == "benchmark"),
            "matrix_benchmarks": sum(1 for row in rows if row["artifact_kind"] == "matrix_benchmark"),
            "matrix_benchmark_exports": sum(1 for row in rows if row["artifact_kind"] == "matrix_benchmark_export"),
            "matrix_benchmark_comparisons": sum(
                1 for row in rows if row["artifact_kind"] == "matrix_benchmark_comparison"
            ),
            "matrix_benchmark_comparison_exports": sum(
                1 for row in rows if row["artifact_kind"] == "matrix_benchmark_comparison_export"
            ),
        },
        "rows": rows,
        "output_dirs": index_payload.get("output_dirs", {}),
    }


def _print_deliberation_campaign_dashboard(
    payload: dict[str, Any],
    *,
    as_json: bool = False,
) -> None:
    if as_json:
        _print_json(payload)
        return

    counts = payload.get("counts", {}) if isinstance(payload.get("counts", {}), dict) else {}
    output_dirs = payload.get("output_dirs", {}) if isinstance(payload.get("output_dirs", {}), dict) else {}
    matrix_count = counts.get("matrix_benchmark", counts.get("matrix_benchmarks", 0))
    matrix_export_count = counts.get(
        "matrix_benchmark_exports",
        counts.get("matrix_benchmark_export", 0),
    )
    matrix_comparison_count = counts.get(
        "matrix_benchmark_comparisons",
        counts.get("matrix_benchmark_comparison", 0),
    )
    matrix_comparison_export_count = counts.get(
        "matrix_benchmark_comparison_exports",
        counts.get("matrix_benchmark_comparison_export", 0),
    )
    console.print(
        Panel(
            f"[bold blue]Rows:[/bold blue] {counts.get('total', 0)}\n"
            f"[bold blue]Campaigns:[/bold blue] {counts.get('campaigns', 0)} | "
            f"[bold blue]Comparisons:[/bold blue] {counts.get('comparisons', 0)} | "
            f"[bold blue]Exports:[/bold blue] {counts.get('exports', 0)} | "
            f"[bold blue]Benchmarks:[/bold blue] {counts.get('benchmarks', 0)} | "
            f"[bold blue]Matrix Benchmarks:[/bold blue] {matrix_count} | "
            f"[bold blue]Matrix Exports:[/bold blue] {matrix_export_count} | "
            f"[bold blue]Matrix Comparisons:[/bold blue] {matrix_comparison_count} | "
            f"[bold blue]Matrix Comparison Exports:[/bold blue] {matrix_comparison_export_count}\n"
            f"[bold blue]Kinds:[/bold blue] {', '.join(payload.get('kinds', []))}\n"
            f"[bold blue]Sort:[/bold blue] {payload.get('sort_by', 'created_at')}\n"
            f"[bold blue]Campaign Status:[/bold blue] {payload.get('campaign_status') or 'all'}\n"
            f"[bold blue]Comparable Only:[/bold blue] {'yes' if payload.get('comparable_only') else 'no'}"
        )
    )
    if output_dirs:
        console.print(
            Panel(
                f"[bold blue]Campaign Dir:[/bold blue] {output_dirs.get('campaigns', 'n/a')}\n"
                f"[bold blue]Comparison Dir:[/bold blue] {output_dirs.get('comparisons', 'n/a')}\n"
                f"[bold blue]Export Dir:[/bold blue] {output_dirs.get('exports', 'n/a')}\n"
                f"[bold blue]Benchmark Dir:[/bold blue] {output_dirs.get('benchmarks', 'n/a')}\n"
                f"[bold blue]Matrix Benchmark Dir:[/bold blue] {output_dirs.get('matrix_benchmarks', 'n/a')}\n"
                f"[bold blue]Matrix Export Dir:[/bold blue] {output_dirs.get('matrix_benchmark_exports', 'n/a')}\n"
                f"[bold blue]Matrix Comparison Dir:[/bold blue] {output_dirs.get('matrix_benchmark_comparisons', 'n/a')}\n"
                f"[bold blue]Matrix Comparison Export Dir:[/bold blue] {output_dirs.get('matrix_benchmark_comparison_exports', 'n/a')}"
            )
        )
    table = Table(title="Deliberation Campaign Dashboard", show_lines=False)
    table.add_column("Kind", style="cyan", no_wrap=True)
    table.add_column("ID", style="white", no_wrap=True)
    table.add_column("Created At", style="magenta")
    table.add_column("Status", style="white")
    table.add_column("Comparable", style="green")
    table.add_column("Quality", style="yellow")
    table.add_column("Confidence", style="yellow")
    table.add_column("Runtime", style="white")
    table.add_column("Engine", style="white")
    table.add_column("Path", style="white")
    for row in payload.get("rows", []) if isinstance(payload.get("rows", []), list) else []:
        runtime_summary = row.get("runtime_summary")
        engine_summary = row.get("engine_summary")
        table.add_row(
            str(row.get("artifact_kind", "n/a")),
            str(row.get("artifact_id", "n/a")),
            str(row.get("created_at", "n/a")),
            str(row.get("status", "n/a")),
            "yes" if row.get("comparable") else "no",
            "" if row.get("quality_score_mean") is None else f"{float(row.get('quality_score_mean') or 0.0):.3f}",
            "" if row.get("confidence_level_mean") is None else f"{float(row.get('confidence_level_mean') or 0.0):.3f}",
            _summarize_counter(runtime_summary) if isinstance(runtime_summary, dict) else str(runtime_summary or "n/a"),
            _summarize_counter(engine_summary) if isinstance(engine_summary, dict) else str(engine_summary or "n/a"),
            _shorten_text(str(row.get("artifact_path") or "n/a"), max_length=38),
        )
    console.print(table)


def _print_deliberation_campaign_index(
    payload: dict[str, Any],
    *,
    as_json: bool = False,
) -> None:
    if as_json:
        _print_json(payload)
        return

    counts = payload.get("counts", {}) if isinstance(payload.get("counts", {}), dict) else {}
    output_dirs = payload.get("output_dirs", {}) if isinstance(payload.get("output_dirs", {}), dict) else {}
    matrix_count = counts.get("matrix_benchmarks", counts.get("matrix_benchmark", 0))
    matrix_export_count = counts.get(
        "matrix_benchmark_exports",
        counts.get("matrix_benchmark_export", 0),
    )
    matrix_comparison_count = counts.get(
        "matrix_benchmark_comparisons",
        counts.get("matrix_benchmark_comparison", 0),
    )
    matrix_comparison_export_count = counts.get(
        "matrix_benchmark_comparison_exports",
        counts.get("matrix_benchmark_comparison_export", 0),
    )
    console.print(
        Panel(
            f"[bold blue]Campaigns:[/bold blue] {counts.get('campaigns', 0)}\n"
            f"[bold blue]Comparisons:[/bold blue] {counts.get('comparisons', 0)}\n"
            f"[bold blue]Exports:[/bold blue] {counts.get('exports', 0)}\n"
            f"[bold blue]Benchmarks:[/bold blue] {counts.get('benchmarks', 0)}\n"
            f"[bold blue]Matrix Benchmarks:[/bold blue] {matrix_count}\n"
            f"[bold blue]Matrix Exports:[/bold blue] {matrix_export_count}\n"
            f"[bold blue]Matrix Comparisons:[/bold blue] {matrix_comparison_count}\n"
            f"[bold blue]Matrix Comparison Exports:[/bold blue] {matrix_comparison_export_count}\n"
            f"[bold blue]Limit:[/bold blue] {payload.get('limit', 10)}"
        )
    )
    console.print(
        Panel(
            f"[bold blue]Campaign Dir:[/bold blue] {output_dirs.get('campaigns', 'n/a')}\n"
            f"[bold blue]Comparison Dir:[/bold blue] {output_dirs.get('comparisons', 'n/a')}\n"
            f"[bold blue]Export Dir:[/bold blue] {output_dirs.get('exports', 'n/a')}\n"
            f"[bold blue]Benchmark Dir:[/bold blue] {output_dirs.get('benchmarks', 'n/a')}\n"
            f"[bold blue]Matrix Benchmark Dir:[/bold blue] {output_dirs.get('matrix_benchmarks', 'n/a')}\n"
            f"[bold blue]Matrix Export Dir:[/bold blue] {output_dirs.get('matrix_benchmark_exports', 'n/a')}\n"
            f"[bold blue]Matrix Comparison Dir:[/bold blue] {output_dirs.get('matrix_benchmark_comparisons', 'n/a')}\n"
            f"[bold blue]Matrix Comparison Export Dir:[/bold blue] {output_dirs.get('matrix_benchmark_comparison_exports', 'n/a')}"
        )
    )

    def _print_rows(title: str, items: list[dict[str, Any]], columns: list[tuple[str, str]]) -> None:
        table = Table(title=title, show_lines=False)
        for label, style in columns:
            table.add_column(label, style=style, no_wrap=True)
        for item in items[:5]:
            table.add_row(*[str(item.get(key, "n/a")) for key, _ in columns])
        console.print(table)

    recent = payload.get("recent", {}) if isinstance(payload.get("recent", {}), dict) else {}
    campaigns = recent.get("campaigns", []) if isinstance(recent.get("campaigns", []), list) else []
    comparisons = recent.get("comparisons", []) if isinstance(recent.get("comparisons", []), list) else []
    exports = recent.get("exports", []) if isinstance(recent.get("exports", []), list) else []
    benchmarks = recent.get("benchmarks", []) if isinstance(recent.get("benchmarks", []), list) else []

    _print_rows(
        "Recent Campaigns",
        campaigns,
        [("campaign_id", "cyan"), ("status", "white"), ("sample_count_requested", "green"), ("fallback_guard_applied", "yellow")],
    )
    _print_rows(
        "Recent Comparisons",
        comparisons,
        [("comparison_id", "cyan"), ("campaign_count", "white"), ("comparable", "green"), ("comparison_key", "yellow")],
    )
    _print_rows(
        "Recent Exports",
        exports,
        [("export_id", "cyan"), ("comparison_id", "white"), ("format", "green"), ("content_path", "yellow")],
    )
    _print_rows(
        "Recent Benchmarks",
        benchmarks,
        [("benchmark_id", "cyan"), ("comparison_id", "white"), ("export_id", "green"), ("format", "yellow")],
    )
    matrix_benchmarks = recent.get("matrix_benchmarks", []) if isinstance(recent.get("matrix_benchmarks", []), list) else []
    _print_rows(
        "Recent Matrix Benchmarks",
        matrix_benchmarks,
        [
            ("benchmark_id", "cyan"),
            ("baseline_campaign_id", "white"),
            ("candidate_count", "green"),
            ("mismatch_count", "yellow"),
            ("report_path", "white"),
        ],
    )
    matrix_benchmark_exports = (
        recent.get("matrix_benchmark_exports", [])
        if isinstance(recent.get("matrix_benchmark_exports", []), list)
        else []
    )
    _print_rows(
        "Recent Matrix Exports",
        matrix_benchmark_exports,
        [
            ("export_id", "cyan"),
            ("benchmark_id", "white"),
            ("format", "green"),
            ("content_path", "yellow"),
        ],
    )
    matrix_benchmark_comparisons = (
        recent.get("matrix_benchmark_comparisons", [])
        if isinstance(recent.get("matrix_benchmark_comparisons", []), list)
        else []
    )
    _print_rows(
        "Recent Matrix Comparisons",
        matrix_benchmark_comparisons,
        [
            ("comparison_id", "cyan"),
            ("comparison_mode", "white"),
            ("report_path", "yellow"),
            ("created_at", "white"),
        ],
    )
    matrix_benchmark_comparison_exports = (
        recent.get("matrix_benchmark_comparison_exports", [])
        if isinstance(recent.get("matrix_benchmark_comparison_exports", []), list)
        else []
    )
    _print_rows(
        "Recent Matrix Comparison Exports",
        matrix_benchmark_comparison_exports,
        [
            ("export_id", "cyan"),
            ("comparison_id", "white"),
            ("format", "green"),
            ("content_path", "yellow"),
        ],
    )


def _run_deliberation_campaign_benchmark(
    *,
    topic: str,
    objective: str | None,
    mode: DeliberationMode,
    participants: list[str],
    documents: list[str],
    entities: list[Any],
    interventions: list[str],
    max_agents: int,
    population_size: int | None,
    rounds: int,
    time_horizon: str,
    config_path: str,
    benchmark_path: str,
    sample_count: int,
    stability_runs: int,
    baseline_runtime: RuntimeBackend,
    candidate_runtime: RuntimeBackend,
    allow_fallback: bool,
    baseline_engine_preference: EnginePreference,
    candidate_engine_preference: EnginePreference,
    budget_max: float,
    timeout_seconds: int,
    backend_mode: str | None,
    campaign_output_dir: str | Path,
    comparison_output_dir: str | Path,
    export_output_dir: str | Path,
    benchmark_output_dir: str | Path | None,
    format: str,
) -> dict[str, Any]:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        raise typer.BadParameter("format must be one of: markdown, json.")
    bundle_helper = getattr(deliberation_campaign_core, "run_deliberation_campaign_benchmark_sync", None)
    if not callable(bundle_helper):
        raise typer.BadParameter("The campaign benchmark helper is unavailable in this build.")

    bundle_result = bundle_helper(
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
        budget_max=budget_max,
        timeout_seconds=timeout_seconds,
        benchmark_path=benchmark_path,
        config_path=config_path,
        backend_mode=backend_mode,
        persist=True,
        output_dir=campaign_output_dir,
        comparison_output_dir=comparison_output_dir,
        export_output_dir=export_output_dir,
        format=normalized_format,
    )
    bundle_payload = (
        bundle_result.model_dump(mode="json")
        if hasattr(bundle_result, "model_dump")
        else dict(bundle_result)
    )
    baseline_payload = bundle_payload.get("baseline_campaign", {})
    candidate_payload = bundle_payload.get("candidate_campaign", {})
    comparison_bundle = bundle_payload.get("comparison_bundle", {})
    if isinstance(comparison_bundle, dict) and comparison_bundle:
        comparison_payload = comparison_bundle.get("comparison_report", {})
        audit_payload = comparison_bundle.get("audit", {})
        export_payload = comparison_bundle.get("export", {})
    else:
        comparison_payload = bundle_payload.get("comparison", {})
        audit_payload = bundle_payload.get("audit", {})
        export_payload = bundle_payload.get("export", {})
    benchmark_id = str(
        bundle_payload.get(
            "benchmark_id",
            f"{bundle_payload.get('baseline_campaign_id', baseline_payload.get('campaign_id', 'benchmark'))}__vs__{bundle_payload.get('candidate_campaign_id', candidate_payload.get('campaign_id', 'benchmark'))}",
        )
    )
    benchmark_base_dir = Path(benchmark_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR)
    benchmark_path = _benchmark_report_path(benchmark_id, output_dir=benchmark_base_dir)
    benchmark_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "benchmark_id": benchmark_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(benchmark_base_dir),
        "report_path": str(benchmark_path),
        "benchmark_mode": "comparison",
        "baseline_campaign": baseline_payload,
        "candidate_campaign": candidate_payload,
        "comparison": comparison_payload,
        "audit": audit_payload,
        "export": export_payload,
        "baseline_campaign_id": bundle_payload.get("baseline_campaign_id", baseline_payload.get("campaign_id")),
        "candidate_campaign_id": bundle_payload.get("candidate_campaign_id", candidate_payload.get("campaign_id")),
        "comparison_id": bundle_payload.get("comparison_id", comparison_payload.get("comparison_id")),
        "export_id": bundle_payload.get("export_id", export_payload.get("export_id")),
        "comparison_report_path": bundle_payload.get("comparison_report_path", comparison_payload.get("report_path")),
        "audit_report_path": bundle_payload.get("audit_report_path", audit_payload.get("report_path")),
        "export_manifest_path": bundle_payload.get("export_manifest_path", export_payload.get("manifest_path")),
        "export_content_path": bundle_payload.get("export_content_path", export_payload.get("content_path")),
        "baseline_runtime": bundle_payload.get("baseline_runtime"),
        "candidate_runtime": bundle_payload.get("candidate_runtime"),
        "baseline_engine_preference": bundle_payload.get("baseline_engine_preference"),
        "candidate_engine_preference": bundle_payload.get("candidate_engine_preference"),
        "format": normalized_format,
        "metadata": bundle_payload,
        "persisted": True,
    }
    benchmark_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def _load_deliberation_campaign_comparison_export(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> DeliberationCampaignComparisonExport:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    export_id = _comparison_export_id(comparison_id, format=normalized_format)
    helper = getattr(deliberation_campaign_core, "load_deliberation_campaign_comparison_export", None)
    if callable(helper):
        try:
            return helper(
                export_id,
                output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR,
                include_content=True,
            )
        except FileNotFoundError as exc:
            raise typer.BadParameter(f"No deliberation campaign comparison export found for {comparison_id!r}.") from exc

    manifest_path = (
        Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR)
        / export_id
        / "manifest.json"
    )
    if not manifest_path.is_file():
        raise typer.BadParameter(f"No deliberation campaign comparison export found for {comparison_id!r}.")
    export = DeliberationCampaignComparisonExport.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if export.content_path and Path(export.content_path).is_file():
        export.content = Path(export.content_path).read_text(encoding="utf-8")
    return export


def _materialize_deliberation_campaign_comparison_export(
    comparison_id: str,
    audit: DeliberationCampaignComparisonAudit | dict[str, Any],
    *,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> DeliberationCampaignComparisonExport:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    export_id = _comparison_export_id(comparison_id, format=normalized_format)
    helper = getattr(deliberation_campaign_core, "materialize_deliberation_campaign_comparison_export", None)
    if callable(helper):
        return helper(
            audit,
            format=normalized_format,
            output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR,
            export_id=export_id,
        )

    export = build_deliberation_campaign_comparison_export(
        audit,
        format=normalized_format,
        include_content=True,
    )
    export.export_id = export_id
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR)
    export.output_dir = str(base_dir)
    export_dir = base_dir / export.export_id
    export.manifest_path = str(export_dir / "manifest.json")
    export.content_path = str(export_dir / ("content.md" if normalized_format == "markdown" else "content.json"))
    export.metadata["manifest_path"] = export.manifest_path
    export.metadata["content_path"] = export.content_path
    export.metadata["persisted"] = True
    export_dir.mkdir(parents=True, exist_ok=True)
    Path(export.manifest_path).write_text(
        json.dumps(export.model_dump(mode="json", exclude={"content"}), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if export.content is not None:
        Path(export.content_path).write_text(export.content, encoding="utf-8")
    return export


def _comparison_export_payload(
    export_payload: DeliberationCampaignComparisonExport | dict[str, Any],
) -> dict[str, Any]:
    if hasattr(export_payload, "model_dump"):
        return export_payload.model_dump(mode="json")
    return dict(export_payload)


def _collect_deliberation_campaign_comparison_exports(
    *,
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> list[DeliberationCampaignComparisonExport | dict[str, Any]]:
    helper = getattr(deliberation_campaign_core, "list_deliberation_campaign_comparison_exports", None)
    if callable(helper):
        return list(
            helper(
                limit=limit,
                output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR,
            )
            or []
        )
    return []


def _print_deliberation_campaign_comparison_audit(
    audit: DeliberationCampaignComparisonAudit | dict[str, Any],
    *,
    as_json: bool = False,
) -> None:
    payload = _comparison_audit_payload(audit)
    if as_json:
        _print_json(payload)
        return

    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    panel_body = (
        f"[bold blue]Comparison ID:[/bold blue] {payload.get('comparison_id', 'n/a')}\n"
        f"[bold blue]Comparable:[/bold blue] {'yes' if payload.get('comparable') else 'no'} | "
        f"campaigns={payload.get('campaign_count', 'n/a')} | "
        f"latest={payload.get('latest', 'n/a')}\n"
        f"[bold blue]Mismatch:[/bold blue] {', '.join(payload.get('mismatch_reasons', [])) or 'none'}\n"
        f"[bold blue]Quality:[/bold blue] mean={float(summary.get('quality_score_mean', 0.0) or 0.0):.3f} | "
        f"confidence={float(summary.get('confidence_level_mean', 0.0) or 0.0):.3f}\n"
        f"[bold blue]Samples:[/bold blue] requested={summary.get('sample_count_requested_total', 'n/a')} | "
        f"completed={summary.get('sample_count_completed_total', 'n/a')} | "
        f"failed={summary.get('sample_count_failed_total', 'n/a')}"
    )
    console.print(Panel(panel_body))
    report_path = payload.get("report_path")
    if report_path:
        console.print(f"[bold blue]Report:[/bold blue] {report_path}")

    table = Table(title="Comparison Audit Entries", show_lines=False)
    table.add_column("Campaign ID", style="cyan", no_wrap=True)
    table.add_column("Status", style="white")
    table.add_column("Runtime", style="white")
    table.add_column("Engine", style="white")
    table.add_column("Samples", style="green")
    table.add_column("Score", style="yellow")
    entries = payload.get("entries", []) if isinstance(payload.get("entries"), list) else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        table.add_row(
            str(entry.get("campaign_id", "n/a")),
            str(entry.get("status", "n/a")),
            str(entry.get("runtime_requested", "n/a")),
            str(entry.get("engine_requested", "n/a")),
            f"{entry.get('sample_count_completed', 'n/a')}/{entry.get('sample_count_requested', 'n/a')}",
            f"{float(entry.get('quality_score_mean', 0.0) or 0.0):.3f}",
        )
    if entries:
        console.print(table)


def _print_deliberation_campaign_comparison_export(
    export_payload: DeliberationCampaignComparisonExport | dict[str, Any],
    *,
    as_json: bool = False,
) -> None:
    payload = _comparison_export_payload(export_payload)
    if as_json:
        _print_json(payload)
        return
    if payload.get("content"):
        console.print(str(payload.get("content")))
        return
    console.print(
        Panel(
            f"[bold blue]Export ID:[/bold blue] {payload.get('export_id', 'n/a')}\n"
            f"[bold blue]Comparison ID:[/bold blue] {payload.get('comparison_id', 'n/a')}\n"
            f"[bold blue]Format:[/bold blue] {payload.get('format', 'n/a')}\n"
            f"[bold blue]Content Path:[/bold blue] {payload.get('content_path', 'n/a')}"
        )
    )


def _print_deliberation_campaign_comparison_export_list(
    exports: list[DeliberationCampaignComparisonExport | dict[str, Any]],
    *,
    output_dir: str | Path | None = None,
    limit: int = 20,
    as_json: bool = False,
) -> None:
    payload = {
        "count": len(exports),
        "limit": limit,
        "output_dir": str(Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR)),
        "exports": [_comparison_export_payload(export) for export in exports],
    }
    if as_json:
        _print_json(payload)
        return
    console.print(
        Panel(
            f"[bold blue]Output Dir:[/bold blue] {payload['output_dir']}\n"
            f"[bold blue]Count:[/bold blue] {payload['count']} (limit={payload['limit']})"
        )
    )
    table = Table(title="Deliberation Campaign Comparison Exports", show_lines=False)
    table.add_column("Export ID", style="cyan", no_wrap=True)
    table.add_column("Comparison ID", style="cyan", no_wrap=True)
    table.add_column("Format", style="white")
    table.add_column("Created At", style="magenta")
    table.add_column("Path", style="green")
    for export in payload["exports"]:
        table.add_row(
            str(export.get("export_id", "n/a")),
            str(export.get("comparison_id", "n/a")),
            str(export.get("format", "n/a")),
            str(export.get("created_at", "n/a")),
            _shorten_text(str(export.get("content_path", "n/a")), max_length=48),
        )
    console.print(table)


def _print_deliberation_interview_result(
    result: DeliberationInterviewResponse,
    *,
    as_json: bool = False,
) -> None:
    if as_json:
        _print_json(result.model_dump(mode="json"))
        return

    console.print(
        Panel(
            f"[bold blue]Deliberation ID:[/bold blue] {result.deliberation_id}\n"
            f"[bold blue]Target:[/bold blue] {result.target_id}\n"
            f"[bold blue]Type:[/bold blue] {result.target_type.value}\n"
            f"[bold blue]Question:[/bold blue] {result.question}"
        )
    )
    console.print(f"[bold green]Answer:[/bold green] {result.answer}")
    if result.references:
        console.print("[bold blue]References:[/bold blue]")
        for item in result.references[:5]:
            console.print(f"- {item}")


def _dump_prediction_markets_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        if hasattr(value, "model_dump"):
            normalized[key] = value.model_dump(mode="json")
        elif isinstance(value, list):
            normalized[key] = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in value]
        else:
            normalized[key] = value
    return normalized


def _print_prediction_markets_payload(payload: dict[str, Any], *, as_json: bool = False) -> None:
    normalized = _dump_prediction_markets_payload(payload)
    if as_json:
        _print_json(normalized)
        return

    forecast = normalized.get("forecast", {})
    recommendation = normalized.get("recommendation", {})
    snapshot = normalized.get("snapshot", {})
    console.print(
        Panel(
            f"[bold blue]Run ID:[/bold blue] {normalized.get('run_id', 'n/a')}\n"
            f"[bold blue]Market ID:[/bold blue] {normalized.get('descriptor', {}).get('market_id', 'n/a')}\n"
            f"[bold blue]Question:[/bold blue] {normalized.get('descriptor', {}).get('question', 'n/a')}\n"
            f"[bold blue]Market Midpoint:[/bold blue] {snapshot.get('midpoint_yes', 'n/a')}\n"
            f"[bold blue]Forecast YES:[/bold blue] {forecast.get('probability_yes', 'n/a')}\n"
            f"[bold blue]Recommendation:[/bold blue] {recommendation.get('action', 'n/a')}\n"
            f"[bold blue]Edge:[/bold blue] {recommendation.get('edge', 'n/a')}"
        )
    )
    if recommendation.get("rationale"):
        console.print(f"[bold green]Rationale:[/bold green] {recommendation['rationale']}")


def _load_json_file(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _resolve_prediction_markets_decision_packet(
    *,
    decision_packet_path: str | None = None,
    deliberation_id: str | None = None,
) -> dict[str, Any] | None:
    if decision_packet_path:
        return _load_json_file(decision_packet_path)
    if not deliberation_id:
        return None
    result = load_deliberation_result(deliberation_id)
    if result.decision_packet is None:
        raise typer.BadParameter(f"Deliberation {deliberation_id} has no persisted decision_packet.")
    if hasattr(result.decision_packet, "model_dump"):
        return result.decision_packet.model_dump(mode="json")
    if isinstance(result.decision_packet, dict):
        return dict(result.decision_packet)
    raise typer.BadParameter(f"Unsupported decision_packet payload for deliberation {deliberation_id}.")


def _collect_prediction_market_runs(*, limit: int = 20, base_dir: str | Path | None = None) -> dict[str, Any]:
    registry = RunRegistry(base_dir)
    runs = [entry.model_dump(mode="json") for entry in registry.recent(limit=limit)]
    return {
        "count": len(runs),
        "limit": limit,
        "runs": runs,
    }


def _parse_entity_values(values: list[str]) -> list[Any]:
    parsed: list[Any] = []
    for value in values:
        candidate = value.strip()
        if not candidate:
            continue
        try:
            parsed.append(json.loads(candidate))
        except json.JSONDecodeError:
            parsed.append({"value": candidate})
    return parsed


def _read_orchestrator_runtime_config(config_path: str = "config.yaml") -> dict[str, Any]:
    path = Path(config_path)
    openclaw_exists = DEFAULT_OPENCLAW_CONFIG_PATH.exists()
    if not path.exists():
        return {
            "config_path": str(path.resolve()),
            "config_exists": False,
            "openclaw_config_path": str(DEFAULT_OPENCLAW_CONFIG_PATH),
            "openclaw_config_exists": openclaw_exists,
            "runtime_requested": RuntimeBackend.pydanticai.value,
            "allow_fallback": True,
        }
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return {
            "config_path": str(path.resolve()),
            "config_exists": True,
            "openclaw_config_path": str(DEFAULT_OPENCLAW_CONFIG_PATH),
            "openclaw_config_exists": openclaw_exists,
            "runtime_requested": RuntimeBackend.pydanticai.value,
            "allow_fallback": True,
            "config_error": str(exc),
        }

    orchestrator = config.get("orchestrator", {}) if isinstance(config.get("orchestrator", {}), dict) else {}
    return {
        "config_path": str(path.resolve()),
        "config_exists": True,
        "openclaw_config_path": str(DEFAULT_OPENCLAW_CONFIG_PATH),
        "openclaw_config_exists": openclaw_exists,
        "runtime_requested": normalize_runtime_backend(
            orchestrator.get("runtime", RuntimeBackend.pydanticai.value)
        ).value,
        "allow_fallback": bool(orchestrator.get("allow_fallback", True)),
    }


def _extract_intent_runtime_metadata(intent: dict[str, Any] | None) -> dict[str, Any]:
    payload = intent if isinstance(intent, dict) else {}
    policy = payload.get("policy", {}) if isinstance(payload.get("policy", {}), dict) else {}
    constraints = payload.get("constraints", {}) if isinstance(payload.get("constraints", {}), dict) else {}
    return {
        "task_type": payload.get("task_type"),
        "engine_preference": policy.get("engine_preference"),
        "budget_max": policy.get("budget_max"),
        "timeout_seconds": policy.get("timeout_seconds"),
        "max_agents": constraints.get("max_agents"),
        "time_horizon": constraints.get("time_horizon"),
    }


def _extract_mission_runtime_metadata(values: dict[str, Any]) -> dict[str, Any]:
    task_ledger = values.get("task_ledger", {}) if isinstance(values.get("task_ledger", {}), dict) else {}
    progress = values.get("progress_ledger", {}) if isinstance(values.get("progress_ledger", {}), dict) else {}
    intent = task_ledger.get("current_intent", {}) if isinstance(task_ledger.get("current_intent", {}), dict) else {}
    sim_result = task_ledger.get("simulation_result") or progress.get("simulation_result")
    metadata = {
        "mission_runtime": "langgraph",
        "orchestrator_runtime": progress.get("orchestrator_runtime"),
        "orchestrator_fallback_used": bool(progress.get("orchestrator_fallback_used", False)),
        "simulation_run_id": values.get("simulation_run_id") or progress.get("simulation_run_id"),
        "simulation_status": values.get("simulation_status")
        or (sim_result.get("status") if isinstance(sim_result, dict) else None),
    }
    metadata.update(_extract_intent_runtime_metadata(intent))
    return metadata


def collect_mission_status_payload(thread_id: str, *, graph: Any | None = None) -> dict[str, Any]:
    active_graph = graph or compile_graph()
    state = active_graph.get_state(build_status_config(thread_id))

    if not state.values:
        return {
            "thread_id": thread_id,
            "found": False,
            "state": None,
            "next_nodes": [],
            "runtime_metadata": {
                "mission_runtime": "langgraph",
                "orchestrator_runtime": None,
                "orchestrator_fallback_used": False,
            },
            "message": "No mission state found for this thread.",
        }

    values = state.values
    task_ledger = values.get("task_ledger", {}) if isinstance(values.get("task_ledger", {}), dict) else {}
    progress = values.get("progress_ledger", {}) if isinstance(values.get("progress_ledger", {}), dict) else {}
    return {
        "thread_id": thread_id,
        "found": True,
        "state": {
            "goal": task_ledger.get("goal"),
            "current_intent": task_ledger.get("current_intent", {}),
            "progress": progress,
            "simulation_result": task_ledger.get("simulation_result") or progress.get("simulation_result"),
            "tokens_used_total": values.get("tokens_used_total", 0),
        },
        "next_nodes": list(state.next or []),
        "runtime_metadata": _extract_mission_runtime_metadata(values),
    }


def _collect_runtime_health_snapshot(runtime_name: str) -> dict:
    selected = str(runtime_name).strip().lower()
    runtime_config = _read_orchestrator_runtime_config()
    if selected == "all":
        runtimes = {
            "langgraph": _collect_runtime_health_snapshot("langgraph"),
            "pydanticai": _collect_runtime_health_snapshot("pydanticai"),
            "legacy": _collect_runtime_health_snapshot("legacy"),
        }
        requested_runtime = runtime_config["runtime_requested"]
        requested_report = runtimes.get(requested_runtime, {})
        effective_runtime = requested_runtime
        if requested_report.get("status") != "healthy" and runtime_config["allow_fallback"]:
            fallback_runtime = requested_report.get("fallback_runtime")
            if fallback_runtime and runtimes.get(fallback_runtime, {}).get("status") == "healthy":
                effective_runtime = fallback_runtime
        return {
            "config": runtime_config,
            "runtimes": runtimes,
            "summary": {
                "mission_runtime": "langgraph",
                "runtime_requested": requested_runtime,
                "runtime_effective_if_invoked": effective_runtime,
                "fallback_enabled": runtime_config["allow_fallback"],
            },
        }
    if selected == "langgraph":
        try:
            compile_graph()
            return {
                "runtime": "langgraph",
                "status": "healthy",
                "configured": True,
                "imports_available": True,
                "message": "LangGraph runtime compiled successfully.",
            }
        except Exception as exc:
            return {
                "runtime": "langgraph",
                "status": "unavailable",
                "configured": False,
                "imports_available": False,
                "message": str(exc),
            }
    return runtime_health(selected)


def _print_runtime_health_report(report: dict, *, as_json: bool = False) -> None:
    if as_json:
        _print_json(report)
        return
    if "runtime" not in report:
        summary = report.get("summary", {})
        config = report.get("config", {})
        console.print(
            Panel(
                f"[bold blue]Mission Runtime:[/bold blue] {summary.get('mission_runtime', 'langgraph')}\n"
                f"[bold blue]Runtime Requested:[/bold blue] {summary.get('runtime_requested', 'unknown')}\n"
                f"[bold blue]Runtime Effective If Invoked:[/bold blue] {summary.get('runtime_effective_if_invoked', 'unknown')}\n"
                f"[bold blue]Fallback Enabled:[/bold blue] {'yes' if summary.get('fallback_enabled') else 'no'}\n"
                f"[bold blue]Config Path:[/bold blue] {config.get('config_path', 'n/a')}"
            )
        )
        table = Table(title="Runtime Health", show_lines=False)
        table.add_column("Runtime", style="cyan", no_wrap=True)
        table.add_column("Status", style="white")
        table.add_column("Provider / Probe", style="magenta")
        table.add_column("Message", style="white")
        for runtime_name, runtime_report in report.get("runtimes", {}).items():
            table.add_row(
                runtime_name,
                str(runtime_report.get("status", "unknown")),
                str(runtime_report.get("provider_base_url") or runtime_report.get("provider_probe_url") or "n/a"),
                str(runtime_report.get("message", "n/a")),
            )
        console.print(table)
        return
    console.print(
        Panel(
            f"[bold blue]Runtime:[/bold blue] {report.get('runtime', 'unknown')}\n"
            f"[bold blue]Status:[/bold blue] {report.get('status', 'unknown')}\n"
            f"[bold blue]Configured:[/bold blue] {'yes' if report.get('configured') else 'no'}\n"
            f"[bold blue]Imports Available:[/bold blue] {'yes' if report.get('imports_available') else 'no'}\n"
            f"[bold blue]Model:[/bold blue] {report.get('model_name', 'n/a')}\n"
            f"[bold blue]Provider Source:[/bold blue] {report.get('provider_source', 'n/a')}\n"
            f"[bold blue]Provider Base URL:[/bold blue] {report.get('provider_base_url', 'n/a')}\n"
            f"[bold blue]Fallback Runtime:[/bold blue] {report.get('fallback_runtime', 'n/a')}\n"
            f"[bold blue]Provider Reachable:[/bold blue] {report.get('provider_reachable', 'n/a')}\n"
            f"[bold blue]HTTP Status:[/bold blue] {report.get('http_status', 'n/a')}\n"
            f"[bold blue]Latency (ms):[/bold blue] {report.get('latency_ms', 'n/a')}\n"
            f"[bold blue]Message:[/bold blue] {report.get('message', 'n/a')}"
        )
    )


def _print_runtime_banner(runtime: RuntimeBackend, *, allow_fallback: bool, label: str) -> None:
    selected = normalize_runtime_backend(runtime)
    console.print(
        f"[bold blue]{label} Runtime:[/bold blue] {selected.value}"
        f" [dim](fallback {'enabled' if allow_fallback else 'disabled'})[/dim]"
    )


def _coerce_runtime_option(runtime: object, allow_fallback: object) -> tuple[RuntimeBackend, bool]:
    selected_runtime = RuntimeBackend.pydanticai
    if isinstance(runtime, RuntimeBackend):
        selected_runtime = runtime
    elif not isinstance(runtime, OptionInfo):
        selected_runtime = normalize_runtime_backend(runtime)  # type: ignore[arg-type]

    resolved_allow_fallback = True
    if isinstance(allow_fallback, bool):
        resolved_allow_fallback = allow_fallback
    elif not isinstance(allow_fallback, OptionInfo):
        resolved_allow_fallback = bool(allow_fallback)

    return selected_runtime, resolved_allow_fallback


def _resolve_stability_runs_option(stability_runs: object) -> int:
    if isinstance(stability_runs, OptionInfo):
        return 1
    resolved_stability_runs = int(stability_runs)
    return max(1, resolved_stability_runs)


def _as_improvement_runtime(runtime: RuntimeBackend | str) -> ImprovementRuntime:
    return ImprovementRuntime(normalize_runtime_backend(runtime).value)


def _resolve_harness_profile_options(
    *,
    interactive: bool,
    full: bool,
    benchmark_profile: BenchmarkProfile,
    backend_mode: str | None,
) -> tuple[BenchmarkProfile, str | None]:
    resolved_interactive = False if isinstance(interactive, OptionInfo) else bool(interactive)
    resolved_full = False if isinstance(full, OptionInfo) else bool(full)
    resolved_backend_mode = None if isinstance(backend_mode, OptionInfo) else backend_mode
    if resolved_interactive and resolved_full:
        raise typer.BadParameter("Use either --interactive or --full, not both.")
    if resolved_full:
        return BenchmarkProfile.full, resolved_backend_mode
    if not resolved_interactive:
        return benchmark_profile, resolved_backend_mode
    return BenchmarkProfile.interactive, resolved_backend_mode or "surrogate"


def _get_improvement_controller(
    *,
    runtime: RuntimeBackend | str = RuntimeBackend.pydanticai,
    allow_fallback: bool = True,
):
    return build_default_controller(
        runtime=_as_improvement_runtime(runtime),
        allow_fallback=allow_fallback,
    )


@harness_app.command("inspect")
def harness_inspect(
    json_output: bool = typer.Option(False, "--json", help="Print the harness inspection as JSON."),
    config_path: str = typer.Option("config.yaml", help="Path to the swarm config."),
    benchmark_path: str | None = typer.Option(None, "--benchmark-path", help="Optional path to a benchmark suite JSON. Overrides --benchmark-profile when set."),
    interactive: bool = typer.Option(False, "--interactive", help="Shortcut for --benchmark-profile interactive with a surrogate backend."),
    full: bool = typer.Option(False, "--full", help="Shortcut for --benchmark-profile full."),
    benchmark_profile: BenchmarkProfile = typer.Option(
        BenchmarkProfile.full,
        "--benchmark-profile",
        help="Benchmark profile. Use 'interactive' for a compact local suite.",
    ),
    memory_path: str = typer.Option(str(DEFAULT_HARNESS_MEMORY_PATH), help="Path to the harness memory SQLite DB."),
    backend_mode: str | None = typer.Option(
        None,
        "--backend-mode",
        help="Force simulation backend mode (live, surrogate, disabled). Defaults to surrogate for the interactive profile.",
    ),
) -> None:
    """Inspect the current harness snapshot, suite, memory, and adapter registration."""
    benchmark_profile, backend_mode = _resolve_harness_profile_options(
        interactive=interactive,
        full=full,
        benchmark_profile=benchmark_profile,
        backend_mode=backend_mode,
    )
    inspection = inspect_harness(
        config_path=config_path,
        benchmark_path=benchmark_path,
        benchmark_profile=benchmark_profile,
        memory_path=memory_path,
        backend_mode=backend_mode,
    )
    _print_harness_inspection(inspection, as_json=json_output)


@harness_app.command("suggest")
def harness_suggest(
    json_output: bool = typer.Option(False, "--json", help="Print the optimization round as JSON."),
    config_path: str = typer.Option("config.yaml", help="Path to the swarm config."),
    benchmark_path: str | None = typer.Option(None, "--benchmark-path", help="Optional path to a benchmark suite JSON. Overrides --benchmark-profile when set."),
    interactive: bool = typer.Option(False, "--interactive", help="Shortcut for --benchmark-profile interactive with a surrogate backend."),
    full: bool = typer.Option(False, "--full", help="Shortcut for --benchmark-profile full."),
    benchmark_profile: BenchmarkProfile = typer.Option(
        BenchmarkProfile.full,
        "--benchmark-profile",
        help="Benchmark profile. Use 'interactive' for a compact local suite.",
    ),
    memory_path: str = typer.Option(str(DEFAULT_HARNESS_MEMORY_PATH), help="Path to the harness memory SQLite DB."),
    run_mapping_path: str = typer.Option(str(DEFAULT_HARNESS_RUN_MAPPING_PATH), help="Path to the harness run-mapping SQLite DB."),
    backend_mode: str | None = typer.Option(
        None,
        "--backend-mode",
        help="Force simulation backend mode (live, surrogate, disabled). Defaults to surrogate for the interactive profile.",
    ),
    runtime: RuntimeBackend = typer.Option(RuntimeBackend.pydanticai, "--runtime", help="Preferred runtime backend."),
    allow_fallback: bool = typer.Option(True, "--allow-fallback/--no-allow-fallback", help="Allow legacy fallback when the preferred runtime is unavailable."),
) -> None:
    """Run one safe suggest-only optimization round."""
    runtime, allow_fallback = _coerce_runtime_option(runtime, allow_fallback)
    benchmark_profile, backend_mode = _resolve_harness_profile_options(
        interactive=interactive,
        full=full,
        benchmark_profile=benchmark_profile,
        backend_mode=backend_mode,
    )
    if not json_output:
        _print_runtime_banner(runtime, allow_fallback=allow_fallback, label="Harness")
    result = run_harness_optimization(
        config_path=config_path,
        benchmark_path=benchmark_path,
        benchmark_profile=benchmark_profile,
        memory_path=memory_path,
        run_mapping_path=run_mapping_path,
        mode=OptimizationMode.suggest_only,
        backend_mode=backend_mode,
        runtime=runtime.value,
        allow_fallback=allow_fallback,
    )
    _print_harness_round(result, as_json=json_output)


@harness_app.command("optimize")
def harness_optimize(
    json_output: bool = typer.Option(False, "--json", help="Print the optimization round as JSON."),
    config_path: str = typer.Option("config.yaml", help="Path to the swarm config."),
    benchmark_path: str | None = typer.Option(None, "--benchmark-path", help="Optional path to a benchmark suite JSON. Overrides --benchmark-profile when set."),
    interactive: bool = typer.Option(False, "--interactive", help="Shortcut for --benchmark-profile interactive with a surrogate backend."),
    full: bool = typer.Option(False, "--full", help="Shortcut for --benchmark-profile full."),
    benchmark_profile: BenchmarkProfile = typer.Option(
        BenchmarkProfile.full,
        "--benchmark-profile",
        help="Benchmark profile. Use 'interactive' for a compact local suite.",
    ),
    memory_path: str = typer.Option(str(DEFAULT_HARNESS_MEMORY_PATH), help="Path to the harness memory SQLite DB."),
    run_mapping_path: str = typer.Option(str(DEFAULT_HARNESS_RUN_MAPPING_PATH), help="Path to the harness run-mapping SQLite DB."),
    safe_auto_apply: bool = typer.Option(False, "--safe-auto-apply", help="Allow auto-apply for low-risk improvements that beat the threshold."),
    backend_mode: str | None = typer.Option(
        None,
        "--backend-mode",
        help="Force simulation backend mode (live, surrogate, disabled). Defaults to surrogate for the interactive profile.",
    ),
    runtime: RuntimeBackend = typer.Option(RuntimeBackend.pydanticai, "--runtime", help="Preferred runtime backend."),
    allow_fallback: bool = typer.Option(True, "--allow-fallback/--no-allow-fallback", help="Allow legacy fallback when the preferred runtime is unavailable."),
) -> None:
    """Run one optimization round. Defaults to suggest-only until explicitly promoted."""
    runtime, allow_fallback = _coerce_runtime_option(runtime, allow_fallback)
    benchmark_profile, backend_mode = _resolve_harness_profile_options(
        interactive=interactive,
        full=full,
        benchmark_profile=benchmark_profile,
        backend_mode=backend_mode,
    )
    if not json_output:
        _print_runtime_banner(runtime, allow_fallback=allow_fallback, label="Harness")
    result = run_harness_optimization(
        config_path=config_path,
        benchmark_path=benchmark_path,
        benchmark_profile=benchmark_profile,
        memory_path=memory_path,
        run_mapping_path=run_mapping_path,
        mode=OptimizationMode.safe_auto_apply if safe_auto_apply else OptimizationMode.suggest_only,
        backend_mode=backend_mode,
        runtime=runtime.value,
        allow_fallback=allow_fallback,
    )
    _print_harness_round(result, as_json=json_output)


@improve_app.command("targets")
def improve_targets(
    json_output: bool = typer.Option(False, "--json", help="Print the target registry as JSON."),
) -> None:
    """List available generic improvement-loop targets."""
    controller = _get_improvement_controller()
    _print_target_descriptors(controller.list_targets(), as_json=json_output)


@improve_app.command("inspect")
def improve_inspect(
    target: str = typer.Option("harness", "--target", help="Target identifier to inspect."),
    json_output: bool = typer.Option(False, "--json", help="Print inspection as JSON."),
    interactive: bool = typer.Option(False, "--interactive", help="Harness-only shortcut for --benchmark-profile interactive with a surrogate backend."),
    full: bool = typer.Option(False, "--full", help="Harness-only shortcut for --benchmark-profile full."),
    benchmark_profile: BenchmarkProfile = typer.Option(
        BenchmarkProfile.full,
        "--benchmark-profile",
        help="Harness-only benchmark profile override. Ignored by targets that do not support it.",
    ),
    backend_mode: str | None = typer.Option(
        None,
        "--backend-mode",
        help="Harness-only backend override (live, surrogate, disabled). Ignored by targets that do not support it.",
    ),
    runtime: RuntimeBackend = typer.Option(RuntimeBackend.pydanticai, "--runtime", help="Preferred runtime backend."),
    allow_fallback: bool = typer.Option(True, "--allow-fallback/--no-allow-fallback", help="Allow legacy fallback when the preferred runtime is unavailable."),
) -> None:
    """Inspect the current state of a generic improvement target."""
    controller = _get_improvement_controller(runtime=runtime, allow_fallback=allow_fallback)
    runtime, allow_fallback = _coerce_runtime_option(runtime, allow_fallback)
    if target == "harness":
        benchmark_profile, backend_mode = _resolve_harness_profile_options(
            interactive=interactive,
            full=full,
            benchmark_profile=benchmark_profile,
            backend_mode=backend_mode,
        )
    if not json_output:
        _print_runtime_banner(runtime, allow_fallback=allow_fallback, label="Improve")
    inspection = controller.inspect_target(
        target,
        runtime=_as_improvement_runtime(runtime),
        allow_fallback=allow_fallback,
        benchmark_profile=benchmark_profile,
        backend_mode=backend_mode,
    )
    inspection.metadata.setdefault("runtime_requested", runtime.value)
    _print_improvement_inspection(inspection, as_json=json_output)


@improve_app.command("round")
def improve_round(
    target: str = typer.Option("harness", "--target", help="Target identifier to optimize."),
    mode: LoopMode = typer.Option(LoopMode.suggest_only, "--mode", help="Round execution mode."),
    json_output: bool = typer.Option(False, "--json", help="Print round result as JSON."),
    interactive: bool = typer.Option(False, "--interactive", help="Harness-only shortcut for --benchmark-profile interactive with a surrogate backend."),
    full: bool = typer.Option(False, "--full", help="Harness-only shortcut for --benchmark-profile full."),
    benchmark_profile: BenchmarkProfile = typer.Option(
        BenchmarkProfile.full,
        "--benchmark-profile",
        help="Harness-only benchmark profile override. Ignored by targets that do not support it.",
    ),
    backend_mode: str | None = typer.Option(
        None,
        "--backend-mode",
        help="Harness-only backend override (live, surrogate, disabled). Ignored by targets that do not support it.",
    ),
    runtime: RuntimeBackend = typer.Option(RuntimeBackend.pydanticai, "--runtime", help="Preferred runtime backend."),
    allow_fallback: bool = typer.Option(True, "--allow-fallback/--no-allow-fallback", help="Allow legacy fallback when the preferred runtime is unavailable."),
) -> None:
    """Run a single generic improvement round for a target."""
    controller = _get_improvement_controller(runtime=runtime, allow_fallback=allow_fallback)
    runtime, allow_fallback = _coerce_runtime_option(runtime, allow_fallback)
    if target == "harness":
        benchmark_profile, backend_mode = _resolve_harness_profile_options(
            interactive=interactive,
            full=full,
            benchmark_profile=benchmark_profile,
            backend_mode=backend_mode,
        )
    if not json_output:
        _print_runtime_banner(runtime, allow_fallback=allow_fallback, label="Improve")
    record = controller.run_round(
        target,
        mode=mode,
        runtime=_as_improvement_runtime(runtime),
        allow_fallback=allow_fallback,
        benchmark_profile=benchmark_profile,
        backend_mode=backend_mode,
    )
    record.metadata.setdefault("runtime_requested", runtime.value)
    _print_improvement_round(record, as_json=json_output)


@improve_app.command("loop")
def improve_loop(
    target: str = typer.Option("harness", "--target", help="Target identifier to optimize."),
    mode: LoopMode = typer.Option(LoopMode.suggest_only, "--mode", help="Loop execution mode."),
    max_rounds: int = typer.Option(3, "--max-rounds", min=1, help="Maximum number of rounds to run."),
    json_output: bool = typer.Option(False, "--json", help="Print loop result as JSON."),
    interactive: bool = typer.Option(False, "--interactive", help="Harness-only shortcut for --benchmark-profile interactive with a surrogate backend."),
    full: bool = typer.Option(False, "--full", help="Harness-only shortcut for --benchmark-profile full."),
    benchmark_profile: BenchmarkProfile = typer.Option(
        BenchmarkProfile.full,
        "--benchmark-profile",
        help="Harness-only benchmark profile override. Ignored by targets that do not support it.",
    ),
    backend_mode: str | None = typer.Option(
        None,
        "--backend-mode",
        help="Harness-only backend override (live, surrogate, disabled). Ignored by targets that do not support it.",
    ),
    runtime: RuntimeBackend = typer.Option(RuntimeBackend.pydanticai, "--runtime", help="Preferred runtime backend."),
    allow_fallback: bool = typer.Option(True, "--allow-fallback/--no-allow-fallback", help="Allow legacy fallback when the preferred runtime is unavailable."),
) -> None:
    """Run a bounded multi-round improvement loop for a target."""
    controller = _get_improvement_controller(runtime=runtime, allow_fallback=allow_fallback)
    runtime, allow_fallback = _coerce_runtime_option(runtime, allow_fallback)
    if target == "harness":
        benchmark_profile, backend_mode = _resolve_harness_profile_options(
            interactive=interactive,
            full=full,
            benchmark_profile=benchmark_profile,
            backend_mode=backend_mode,
        )
    if not json_output:
        _print_runtime_banner(runtime, allow_fallback=allow_fallback, label="Improve")
    run = controller.run_loop(
        target,
        mode=mode,
        max_rounds=max_rounds,
        runtime=_as_improvement_runtime(runtime),
        allow_fallback=allow_fallback,
        benchmark_profile=benchmark_profile,
        backend_mode=backend_mode,
    )
    for record in run.rounds:
        record.metadata.setdefault("runtime_requested", runtime.value)
    _print_improvement_loop(run, as_json=json_output)


@app.command("runtime-health")
def runtime_health_command(
    runtime_name: str = typer.Option("all", "--runtime", help="Runtime to inspect: all, langgraph, pydanticai, legacy."),
    json_output: bool = typer.Option(False, "--json", help="Print runtime health as JSON."),
):
    """Inspect runtime/provider health for the main execution backends."""
    _print_runtime_health_report(_collect_runtime_health_snapshot(runtime_name), as_json=json_output)

def get_graph_and_config():
    graph = compile_graph()
    config = {"configurable": {"thread_id": "default_mission"}}
    return graph, config


def _run_graph(
    goal: str,
    thread_id: str,
    source: str,
    *,
    task_type: TaskType = TaskType.analysis,
    max_agents: int = 1000,
    time_horizon: str = "7d",
    budget_max: float = 10,
    timeout_seconds: int = 1800,
    engine_preference: EnginePreference = EnginePreference.agentsociety,
) -> None:
    graph, config = get_graph_and_config()
    config["configurable"]["thread_id"] = thread_id

    initial_state = build_initial_state(
        goal=goal,
        thread_id=thread_id,
        source=source,
        task_type=task_type,
        max_agents=max_agents,
        time_horizon=time_horizon,
        budget_max=budget_max,
        timeout_seconds=timeout_seconds,
        engine_preference=engine_preference,
    )

    console.print(
        Panel(
            f"[bold green]Starting Mission:[/bold green] {goal}\n"
            f"[bold blue]Thread ID:[/bold blue] {thread_id}\n"
            f"[bold blue]Source:[/bold blue] {source}\n"
            f"[bold blue]Task Type:[/bold blue] {task_type.value}\n"
            f"[bold blue]Engine Preference:[/bold blue] {engine_preference.value}\n"
            f"[bold blue]Budget Max:[/bold blue] {budget_max}\n"
            f"[bold blue]Timeout Seconds:[/bold blue] {timeout_seconds}\n"
            f"[bold blue]Max Agents:[/bold blue] {max_agents}\n"
            f"[bold blue]Time Horizon:[/bold blue] {time_horizon}"
        )
    )

    for event in graph.stream(initial_state, config):
        for node_name, state_update in event.items():
            console.print(f"[bold magenta][{node_name}][/bold magenta] executed.")

            if "task_ledger" in state_update:
                tl = state_update["task_ledger"]
                if tl.get("current_intent"):
                    intent = tl["current_intent"]
                    console.print(f"  → Intent: [bold cyan]{intent.get('intent_id', 'unknown')}[/bold cyan] ({intent.get('task_type', 'unknown')})")
                if tl.get("simulation_result"):
                    sim = tl["simulation_result"]
                    console.print(f"  → Simulation: [bold cyan]{sim.get('status', 'unknown')}[/bold cyan]")

            if "progress_ledger" in state_update:
                pl = state_update["progress_ledger"]
                if pl.get("next_speaker"):
                    console.print(f"  → Delegating to: [bold cyan]{pl['next_speaker']}[/bold cyan]")
                    console.print(f"  → Instruction: {pl.get('instruction', '')[:100]}...")
                if pl.get("simulation_result"):
                    sim = pl["simulation_result"]
                    console.print(f"  → Simulation: [bold cyan]{sim.get('status', 'unknown')}[/bold cyan]")

            if "workers_output" in state_update and state_update["workers_output"]:
                last_out = state_update["workers_output"][-1]
                status = "[green]SUCCESS[/green]" if last_out.get("success") else f"[red]FAILED[/red] ({last_out.get('error')})"
                console.print(f"  → {last_out.get('worker_name')} result: {status}")
                console.print(f"  → Output: {last_out.get('content', '')[:100]}...")

@app.command()
def run(
    goal: str,
    thread_id: str = "default_mission",
    task_type: TaskType = typer.Option(TaskType.analysis, "--task-type", help="Mission intent type."),
    engine_preference: EnginePreference = typer.Option(
        EnginePreference.agentsociety,
        "--engine-preference",
        help="Preferred simulation engine for scenario_simulation intents.",
    ),
    max_agents: int = typer.Option(1000, "--max-agents", help="Max agents for scenario simulation intents."),
    time_horizon: str = typer.Option("7d", "--time-horizon", help="Simulation horizon for scenario intents."),
    budget_max: float = typer.Option(10.0, "--budget-max", help="Budget cap carried in the Swarm intent."),
    timeout_seconds: int = typer.Option(1800, "--timeout-seconds", help="Timeout carried in the Swarm intent."),
):
    """Start a new multi-agent mission."""
    _run_graph(
        goal=goal,
        thread_id=thread_id,
        source="cli",
        task_type=task_type,
        engine_preference=engine_preference,
        max_agents=max_agents,
        time_horizon=time_horizon,
        budget_max=budget_max,
        timeout_seconds=timeout_seconds,
    )


@app.command()
def delegate(
    goal: str,
    thread_id: str = "default_mission",
    task_type: TaskType = typer.Option(TaskType.analysis, "--task-type", help="Mission intent type."),
    engine_preference: EnginePreference = typer.Option(
        EnginePreference.agentsociety,
        "--engine-preference",
        help="Preferred simulation engine for scenario_simulation intents.",
    ),
    max_agents: int = typer.Option(1000, "--max-agents", help="Max agents for scenario simulation intents."),
    time_horizon: str = typer.Option("7d", "--time-horizon", help="Simulation horizon for scenario intents."),
    budget_max: float = typer.Option(10.0, "--budget-max", help="Budget cap carried in the Swarm intent."),
    timeout_seconds: int = typer.Option(1800, "--timeout-seconds", help="Timeout carried in the Swarm intent."),
):
    """Entry point intended for Swarm Core delegation and external MCP callers."""
    _run_graph(
        goal=goal,
        thread_id=thread_id,
        source="mcp",
        task_type=task_type,
        engine_preference=engine_preference,
        max_agents=max_agents,
        time_horizon=time_horizon,
        budget_max=budget_max,
        timeout_seconds=timeout_seconds,
    )


@app.command()
def meeting(
    topic: str,
    objective: str | None = None,
    participants: list[str] = typer.Option([], "--participant", help="Participant to include. Repeat the option to add more participants."),
    max_agents: int = typer.Option(6, "--max-agents", help="Maximum number of participants to include."),
    rounds: int = typer.Option(2, "--rounds", help="Number of discussion rounds to run."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist the meeting artifact to disk."),
    config_path: str = typer.Option("config.yaml", help="Path to the swarm config."),
    runtime: RuntimeBackend = typer.Option(RuntimeBackend.pydanticai, "--runtime", help="Preferred meeting runtime."),
    allow_fallback: bool = typer.Option(True, "--allow-fallback/--no-allow-fallback", help="Allow a legacy fallback if the preferred runtime is unavailable."),
    strict_analysis: bool = typer.Option(True, "--strict-analysis/--no-strict-analysis", help="For analysis meetings, disable silent fallback so the requested runtime is either honored or fails explicitly."),
    json_output: bool = typer.Option(False, "--json", help="Print the meeting result as JSON."),
):
    """Run a multi-agent strategy meeting and synthesize a recommended strategy."""
    runtime, allow_fallback = _coerce_runtime_option(runtime, allow_fallback)
    resolved_strict_analysis = True if isinstance(strict_analysis, OptionInfo) else bool(strict_analysis)
    resolved_allow_fallback = False if resolved_strict_analysis and runtime != RuntimeBackend.legacy else allow_fallback
    resolved_participants = [] if isinstance(participants, OptionInfo) else participants
    resolved_config_path = "config.yaml" if isinstance(config_path, OptionInfo) else config_path
    if not json_output:
        _print_runtime_banner(runtime, allow_fallback=resolved_allow_fallback, label="Meeting")
    result = run_strategy_meeting_runtime(
        topic=topic,
        objective=objective,
        participants=resolved_participants,
        max_agents=max_agents,
        rounds=rounds,
        persist=persist,
        config_path=config_path,
        runtime=runtime,
        allow_fallback=resolved_allow_fallback,
    )
    strict_analysis_metadata = result.metadata.get("strict_analysis")
    if not isinstance(strict_analysis_metadata, dict):
        strict_analysis_metadata = {"enabled": resolved_strict_analysis}
        result.metadata["strict_analysis"] = strict_analysis_metadata
    strict_analysis_metadata.setdefault("enabled", resolved_strict_analysis)
    strict_analysis_metadata.setdefault("requested_allow_fallback", allow_fallback)
    strict_analysis_metadata.setdefault("effective_allow_fallback", resolved_allow_fallback)
    strict_analysis_metadata.setdefault(
        "fallback_guard_applied",
        bool(resolved_strict_analysis and runtime != RuntimeBackend.legacy and allow_fallback),
    )
    comparability = result.metadata.setdefault("comparability", {}) if isinstance(result.metadata, dict) else {}
    if isinstance(comparability, dict):
        comparability.setdefault("run_id", getattr(result, "meeting_id", None))
        comparability.setdefault("config_id", resolved_config_path)
        runtime_id = _first_text_value(
            comparability.get("runtime_id"),
            comparability.get("model_name"),
            comparability.get("provider_base_url"),
            result.metadata.get("model_name") if isinstance(result.metadata, dict) else None,
            result.metadata.get("provider_base_url") if isinstance(result.metadata, dict) else None,
        )
        if runtime_id is not None:
            comparability.setdefault("runtime_id", runtime_id)
        comparability.setdefault("strict_analysis", resolved_strict_analysis)
        comparability.setdefault("strict_requested_allow_fallback", allow_fallback)
        comparability.setdefault("strict_effective_allow_fallback", resolved_allow_fallback)
    _print_strategy_meeting_result(result, as_json=json_output)


@app.command()
def deliberate(
    topic: str,
    objective: str | None = None,
    mode: DeliberationMode = typer.Option(DeliberationMode.committee, "--mode", help="Deliberation mode: committee, simulation, or hybrid."),
    participants: list[str] = typer.Option([], "--participant", help="Participant to include. Repeat the option to add more participants."),
    documents: list[str] = typer.Option([], "--document", help="Document or evidence snippet to ground the deliberation."),
    entities: list[str] = typer.Option([], "--entity", help="Entity payload as JSON or plain text. Repeat to add more entities."),
    interventions: list[str] = typer.Option([], "--intervention", help="Intervention or event injection to test during deliberation."),
    max_agents: int = typer.Option(6, "--max-agents", help="Maximum committee participants or base simulation agent count."),
    population_size: int | None = typer.Option(None, "--population-size", help="Population size for simulation or hybrid modes."),
    rounds: int = typer.Option(2, "--rounds", help="Committee discussion rounds or simulation rounds hint."),
    time_horizon: str = typer.Option("7d", "--time-horizon", help="Simulation horizon for simulation or hybrid modes."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist deliberation artifacts to disk."),
    config_path: str = typer.Option("config.yaml", help="Path to the swarm config."),
    runtime: RuntimeBackend = typer.Option(RuntimeBackend.pydanticai, "--runtime", help="Preferred committee synthesis runtime."),
    allow_fallback: bool = typer.Option(True, "--allow-fallback/--no-allow-fallback", help="Allow a legacy fallback if the preferred runtime is unavailable."),
    engine_preference: EnginePreference = typer.Option(EnginePreference.agentsociety, "--engine-preference", help="Preferred simulation engine."),
    ensemble_engines: list[EnginePreference] = typer.Option([], "--ensemble-engine", help="Additional engines to compare during simulation or hybrid runs."),
    budget_max: float = typer.Option(10.0, "--budget-max", help="Budget cap for simulation-backed modes."),
    timeout_seconds: int = typer.Option(1800, "--timeout-seconds", help="Timeout for simulation-backed modes."),
    benchmark_path: str = typer.Option(str(DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH), "--benchmark-path", help="Benchmark suite path for deliberation evaluation."),
    stability_runs: int = typer.Option(1, "--stability-runs", min=1, help="Repeat the same run and measure stability."),
    strict_analysis: bool = typer.Option(True, "--strict-analysis/--no-strict-analysis", help="Disable silent round trimming and implicit fallback for analytical deliberation runs."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="AgentSociety backend mode: live, surrogate, or disabled."),
    json_output: bool = typer.Option(False, "--json", help="Print the deliberation result as JSON."),
):
    """Run the unified committee, simulation, or hybrid deliberation flow."""
    runtime, allow_fallback = _coerce_runtime_option(runtime, allow_fallback)
    resolved_mode = DeliberationMode.committee if isinstance(mode, OptionInfo) else mode
    resolved_participants = [] if isinstance(participants, OptionInfo) else participants
    resolved_documents = [] if isinstance(documents, OptionInfo) else documents
    resolved_entities = _parse_entity_values([] if isinstance(entities, OptionInfo) else entities)
    resolved_interventions = [] if isinstance(interventions, OptionInfo) else interventions
    resolved_max_agents = 6 if isinstance(max_agents, OptionInfo) else max_agents
    resolved_population_size = None if isinstance(population_size, OptionInfo) else population_size
    resolved_rounds = 2 if isinstance(rounds, OptionInfo) else rounds
    resolved_time_horizon = "7d" if isinstance(time_horizon, OptionInfo) else time_horizon
    resolved_persist = True if isinstance(persist, OptionInfo) else persist
    resolved_config_path = "config.yaml" if isinstance(config_path, OptionInfo) else config_path
    resolved_engine_preference = (
        EnginePreference.agentsociety if isinstance(engine_preference, OptionInfo) else engine_preference
    )
    resolved_ensemble_engines = [] if isinstance(ensemble_engines, OptionInfo) else ensemble_engines
    resolved_budget_max = 10.0 if isinstance(budget_max, OptionInfo) else budget_max
    resolved_timeout_seconds = 1800 if isinstance(timeout_seconds, OptionInfo) else timeout_seconds
    resolved_benchmark_path = (
        str(DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH)
        if isinstance(benchmark_path, OptionInfo)
        else benchmark_path
    )
    resolved_stability_runs = _resolve_stability_runs_option(stability_runs)
    resolved_strict_analysis = True if isinstance(strict_analysis, OptionInfo) else bool(strict_analysis)
    resolved_backend_mode = None if isinstance(backend_mode, OptionInfo) else backend_mode
    stability_guard_applied = resolved_stability_runs > 1 and allow_fallback
    strict_analysis_guard_applied = resolved_strict_analysis and allow_fallback
    resolved_allow_fallback = False if (stability_guard_applied or strict_analysis_guard_applied) else allow_fallback
    if not json_output:
        _print_runtime_banner(runtime, allow_fallback=resolved_allow_fallback, label="Deliberation")
    result = run_deliberation_runtime(
        topic=topic,
        objective=objective,
        mode=resolved_mode.value,
        participants=resolved_participants,
        documents=resolved_documents,
        entities=resolved_entities,
        interventions=resolved_interventions,
        max_agents=resolved_max_agents,
        population_size=resolved_population_size,
        rounds=resolved_rounds,
        time_horizon=resolved_time_horizon,
        persist=resolved_persist,
        config_path=resolved_config_path,
        runtime=runtime,
        allow_fallback=resolved_allow_fallback,
        engine_preference=resolved_engine_preference,
        ensemble_engines=resolved_ensemble_engines,
        budget_max=resolved_budget_max,
        timeout_seconds=resolved_timeout_seconds,
        benchmark_path=resolved_benchmark_path,
        stability_runs=resolved_stability_runs,
        strict_analysis=resolved_strict_analysis,
        backend_mode=resolved_backend_mode,
    )
    comparability = result.metadata.setdefault("comparability", {}) if isinstance(result.metadata, dict) else {}
    if isinstance(comparability, dict):
        comparability.setdefault("run_id", getattr(result, "deliberation_id", None))
        comparability.setdefault("config_id", resolved_config_path)
        runtime_id = _first_text_value(
            comparability.get("runtime_id"),
            comparability.get("model_name"),
            comparability.get("provider_base_url"),
            result.metadata.get("model_name") if isinstance(result.metadata, dict) else None,
            result.metadata.get("provider_base_url") if isinstance(result.metadata, dict) else None,
        )
        if runtime_id is not None:
            comparability.setdefault("runtime_id", runtime_id)
        comparability.setdefault("runtime_requested", result.runtime_requested)
        comparability.setdefault("runtime_used", result.runtime_used)
        comparability.setdefault("fallback_used", result.fallback_used)
        comparability.setdefault("engine_requested", result.engine_requested)
        comparability.setdefault("engine_used", result.engine_used)
        comparability.setdefault("stability_runs", resolved_stability_runs)
        comparability.setdefault("stability_guard_applied", stability_guard_applied)
        comparability.setdefault("strict_analysis", resolved_strict_analysis)
        comparability.setdefault("strict_fallback_guard_applied", strict_analysis_guard_applied)
        comparability.setdefault("strict_requested_allow_fallback", allow_fallback)
        comparability.setdefault("strict_effective_allow_fallback", resolved_allow_fallback)
        comparability.setdefault("strict_rounds_requested", resolved_rounds if resolved_strict_analysis else None)
        stability_summary = getattr(result, "stability_summary", None)
        if stability_summary is not None:
            comparability.setdefault("stability_metric_name", stability_summary.metric_name)
            comparability.setdefault("stability_comparison_key", stability_summary.comparison_key)
            comparability.setdefault("stability_sample_count", stability_summary.sample_count)
    result.metadata.setdefault("stability_runs", resolved_stability_runs)
    result.metadata.setdefault("stability_guard_applied", stability_guard_applied)
    strict_analysis_metadata = result.metadata.get("strict_analysis")
    if not isinstance(strict_analysis_metadata, dict):
        strict_analysis_metadata = {"enabled": resolved_strict_analysis}
        result.metadata["strict_analysis"] = strict_analysis_metadata
    strict_analysis_metadata.setdefault("enabled", resolved_strict_analysis)
    strict_analysis_metadata.setdefault("requested_rounds", resolved_rounds)
    strict_analysis_metadata.setdefault("requested_allow_fallback", allow_fallback)
    strict_analysis_metadata.setdefault("effective_allow_fallback", resolved_allow_fallback)
    strict_analysis_metadata.setdefault("fallback_guard_applied", strict_analysis_guard_applied)
    if stability_guard_applied:
        result.metadata.setdefault(
            "stability_guard_reason",
            "fallback_disabled_for_repeated_stability_comparison",
        )
    if strict_analysis_guard_applied:
        result.metadata.setdefault(
            "strict_analysis_guard_reason",
            "fallback_disabled_for_strict_analysis",
        )
    _print_deliberation_result(result, as_json=json_output)


@app.command("deliberation-campaign")
def deliberation_campaign(
    topic: str,
    objective: str | None = None,
    mode: DeliberationMode = typer.Option(DeliberationMode.committee, "--mode", help="Deliberation mode: committee, simulation, or hybrid."),
    participants: list[str] = typer.Option([], "--participant", help="Participant to include. Repeat the option to add more participants."),
    documents: list[str] = typer.Option([], "--document", help="Document or evidence snippet to ground the deliberation."),
    entities: list[str] = typer.Option([], "--entity", help="Entity payload as JSON or plain text. Repeat to add more entities."),
    interventions: list[str] = typer.Option([], "--intervention", help="Intervention or event injection to test during deliberation."),
    max_agents: int = typer.Option(6, "--max-agents", help="Maximum committee participants or base simulation agent count."),
    population_size: int | None = typer.Option(None, "--population-size", help="Population size for simulation or hybrid modes."),
    rounds: int = typer.Option(2, "--rounds", help="Committee discussion rounds or simulation rounds hint."),
    time_horizon: str = typer.Option("7d", "--time-horizon", help="Simulation horizon for simulation or hybrid modes."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist campaign artifacts to disk."),
    config_path: str = typer.Option("config.yaml", help="Path to the swarm config."),
    runtime: RuntimeBackend = typer.Option(RuntimeBackend.pydanticai, "--runtime", help="Preferred committee synthesis runtime."),
    allow_fallback: bool = typer.Option(True, "--allow-fallback/--no-allow-fallback", help="Allow a legacy fallback if the preferred runtime is unavailable."),
    engine_preference: EnginePreference = typer.Option(EnginePreference.agentsociety, "--engine-preference", help="Preferred simulation engine."),
    ensemble_engines: list[EnginePreference] = typer.Option([], "--ensemble-engine", help="Additional engines to compare during simulation or hybrid runs."),
    budget_max: float = typer.Option(10.0, "--budget-max", help="Budget cap for simulation-backed modes."),
    timeout_seconds: int = typer.Option(1800, "--timeout-seconds", help="Timeout for simulation-backed modes."),
    benchmark_path: str = typer.Option(str(DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH), "--benchmark-path", help="Benchmark suite path for deliberation evaluation."),
    sample_count: int = typer.Option(3, "--sample-count", min=1, help="Number of comparable samples in the outer campaign loop."),
    stability_runs: int = typer.Option(1, "--stability-runs", min=1, help="Number of repeated runs inside each sample for stability scoring."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="AgentSociety backend mode: live, surrogate, or disabled."),
    json_output: bool = typer.Option(False, "--json", help="Print the campaign result as JSON."),
):
    """Run a repeated deliberation campaign and persist a comparable report."""
    runtime, allow_fallback = _coerce_runtime_option(runtime, allow_fallback)
    resolved_mode = DeliberationMode.committee if isinstance(mode, OptionInfo) else mode
    resolved_participants = [] if isinstance(participants, OptionInfo) else participants
    resolved_documents = [] if isinstance(documents, OptionInfo) else documents
    resolved_entities = _parse_entity_values([] if isinstance(entities, OptionInfo) else entities)
    resolved_interventions = [] if isinstance(interventions, OptionInfo) else interventions
    resolved_max_agents = 6 if isinstance(max_agents, OptionInfo) else max_agents
    resolved_population_size = None if isinstance(population_size, OptionInfo) else population_size
    resolved_rounds = 2 if isinstance(rounds, OptionInfo) else rounds
    resolved_time_horizon = "7d" if isinstance(time_horizon, OptionInfo) else time_horizon
    resolved_persist = True if isinstance(persist, OptionInfo) else persist
    resolved_config_path = "config.yaml" if isinstance(config_path, OptionInfo) else config_path
    resolved_engine_preference = (
        EnginePreference.agentsociety if isinstance(engine_preference, OptionInfo) else engine_preference
    )
    resolved_ensemble_engines = [] if isinstance(ensemble_engines, OptionInfo) else ensemble_engines
    resolved_budget_max = 10.0 if isinstance(budget_max, OptionInfo) else budget_max
    resolved_timeout_seconds = 1800 if isinstance(timeout_seconds, OptionInfo) else timeout_seconds
    resolved_benchmark_path = (
        str(DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH)
        if isinstance(benchmark_path, OptionInfo)
        else benchmark_path
    )
    resolved_sample_count = 3 if isinstance(sample_count, OptionInfo) else sample_count
    resolved_stability_runs = 1 if isinstance(stability_runs, OptionInfo) else stability_runs

    report = run_deliberation_campaign_sync(
        topic=topic,
        objective=objective,
        mode=resolved_mode,
        participants=resolved_participants,
        documents=resolved_documents,
        entities=resolved_entities,
        interventions=resolved_interventions,
        max_agents=resolved_max_agents,
        population_size=resolved_population_size,
        rounds=resolved_rounds,
        time_horizon=resolved_time_horizon,
        persist=resolved_persist,
        config_path=resolved_config_path,
        runtime=runtime,
        allow_fallback=allow_fallback,
        engine_preference=resolved_engine_preference,
        ensemble_engines=resolved_ensemble_engines,
        budget_max=resolved_budget_max,
        timeout_seconds=resolved_timeout_seconds,
        benchmark_path=resolved_benchmark_path,
        stability_runs=resolved_stability_runs,
        sample_count=resolved_sample_count,
        backend_mode=backend_mode,
        output_dir=DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR,
        runner=run_deliberation_runtime,
    )
    _print_deliberation_campaign_result(report, as_json=json_output)


@app.command("read-deliberation")
def read_deliberation(
    deliberation_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the stored deliberation result as JSON."),
):
    """Read a persisted deliberation artifact by deliberation id."""
    result = load_deliberation_result(deliberation_id)
    _print_deliberation_result(result, as_json=json_output)


@app.command("read-deliberation-campaign")
def read_deliberation_campaign(
    campaign_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the stored campaign report as JSON."),
):
    """Read a persisted deliberation campaign report by campaign ID."""
    report = _load_deliberation_campaign_report(campaign_id)
    _print_deliberation_campaign_result(report, as_json=json_output)


@app.command("list-deliberation-campaigns")
def list_deliberation_campaigns(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum number of persisted campaign reports to list."),
    status: DeliberationCampaignStatus | None = typer.Option(
        None,
        "--status",
        help="Optional status filter: completed, partial, or failed.",
    ),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign reports.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the campaign list as JSON."),
):
    """List persisted deliberation campaign reports."""
    reports = _collect_deliberation_campaign_reports(limit=limit, output_dir=output_dir, status=status)
    _print_deliberation_campaign_list(
        reports,
        output_dir=output_dir,
        limit=limit,
        status=status,
        as_json=json_output,
    )


@app.command("compare-deliberation-campaigns")
def compare_deliberation_campaigns(
    campaign_ids: list[str] = typer.Argument(
        [],
        metavar="CAMPAIGN_ID",
        help="Two persisted campaign IDs to compare, or use --latest to compare the newest pair.",
    ),
    latest: bool = typer.Option(False, "--latest", help="Compare the two most recent persisted campaigns."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign reports.",
    ),
    persist: bool = typer.Option(
        True,
        "--persist/--no-persist",
        help="Persist the comparison report under the comparison output directory.",
    ),
    comparison_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR),
        "--comparison-output-dir",
        help="Directory used to persist deliberation campaign comparison reports.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the comparison as JSON."),
):
    """Compare two persisted deliberation campaign reports."""
    if latest and campaign_ids:
        raise typer.BadParameter("Use either explicit campaign IDs or --latest, not both.")
    helper = getattr(deliberation_campaign_core, "compare_deliberation_campaign_reports", None)
    if not callable(helper):
        raise typer.BadParameter("The campaign comparison helper is unavailable in this build.")
    if latest:
        report = helper(
            latest=2,
            output_dir=output_dir,
            persist=persist,
            comparison_output_dir=comparison_output_dir,
        )
    else:
        if len(campaign_ids) != 2:
            raise typer.BadParameter("Provide exactly two campaign IDs, or use --latest.")
        report = helper(
            campaign_ids=campaign_ids,
            output_dir=output_dir,
            persist=persist,
            comparison_output_dir=comparison_output_dir,
        )
    _print_deliberation_campaign_comparison(
        report,
        output_dir=comparison_output_dir,
        as_json=json_output,
    )


@app.command("compare-deliberation-campaigns-audit-export")
def compare_deliberation_campaigns_audit_export(
    campaign_ids: list[str] = typer.Argument(
        [],
        metavar="CAMPAIGN_ID",
        help="Two persisted campaign IDs to compare, or use --latest to compare the newest pair.",
    ),
    latest: bool = typer.Option(False, "--latest", help="Compare the two most recent persisted campaigns."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign reports.",
    ),
    comparison_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR),
        "--comparison-output-dir",
        help="Directory used to persist deliberation campaign comparison reports.",
    ),
    export_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR),
        "--export-output-dir",
        help="Directory used to persist deliberation campaign comparison exports.",
    ),
    format: str = typer.Option("markdown", "--format", help="Export format: markdown or json."),
    json_output: bool = typer.Option(False, "--json", help="Print the workflow bundle as JSON."),
):
    """Compare two persisted campaigns, build the audit, and persist the final export."""
    if latest and campaign_ids:
        raise typer.BadParameter("Use either explicit campaign IDs or --latest, not both.")
    bundle_helper = getattr(deliberation_campaign_core, "compare_deliberation_campaign_bundle", None)
    if callable(bundle_helper):
        if latest:
            bundle_result = bundle_helper(
                latest=2,
                output_dir=output_dir,
                persist=True,
                comparison_output_dir=comparison_output_dir,
                export_output_dir=export_output_dir,
                format=format,
            )
        else:
            if len(campaign_ids) != 2:
                raise typer.BadParameter("Provide exactly two campaign IDs, or use --latest.")
            bundle_result = bundle_helper(
                campaign_ids=campaign_ids,
                output_dir=output_dir,
                persist=True,
                comparison_output_dir=comparison_output_dir,
                export_output_dir=export_output_dir,
                format=format,
            )
        bundle_payload = (
            bundle_result.model_dump(mode="json")
            if hasattr(bundle_result, "model_dump")
            else dict(bundle_result)
        )
        comparison_payload = bundle_payload.get("comparison_report", {})
        audit_payload = bundle_payload.get("audit", {})
        export_payload = bundle_payload.get("export", {})
        comparison_id = str(comparison_payload.get("comparison_id", "n/a"))
    else:
        helper = getattr(deliberation_campaign_core, "compare_deliberation_campaign_reports", None)
        if not callable(helper):
            raise typer.BadParameter("The campaign comparison helper is unavailable in this build.")
        if latest:
            comparison_report = helper(
                latest=2,
                output_dir=output_dir,
                persist=True,
                comparison_output_dir=comparison_output_dir,
            )
        else:
            if len(campaign_ids) != 2:
                raise typer.BadParameter("Provide exactly two campaign IDs, or use --latest.")
            comparison_report = helper(
                campaign_ids=campaign_ids,
                output_dir=output_dir,
                persist=True,
                comparison_output_dir=comparison_output_dir,
            )

        comparison_payload = _comparison_report_payload(comparison_report)
        comparison_id = str(comparison_payload.get("comparison_id", "n/a"))
        audit = _load_deliberation_campaign_comparison_audit(
            comparison_id,
            output_dir=comparison_output_dir,
            include_markdown=True,
        )
        export = _materialize_deliberation_campaign_comparison_export(
            comparison_id,
            audit,
            output_dir=export_output_dir,
            format=format,
        )
        audit_payload = _comparison_audit_payload(audit)
        export_payload = _comparison_export_payload(export)

    bundle = {
        "comparison": comparison_payload,
        "audit": audit_payload,
        "export": export_payload,
        "comparison_id": comparison_id,
        "export_id": export_payload.get("export_id"),
        "comparison_report_path": comparison_payload.get("report_path"),
        "audit_report_path": audit_payload.get("report_path"),
        "export_manifest_path": export_payload.get("manifest_path"),
        "export_content_path": export_payload.get("content_path"),
    }
    if json_output:
        _print_json(bundle)
        return
    console.print(
        Panel(
            f"[bold blue]Comparison ID:[/bold blue] {comparison_id}\n"
            f"[bold blue]Export ID:[/bold blue] {bundle.get('export_id', 'n/a')}\n"
            f"[bold blue]Comparison Report:[/bold blue] {bundle.get('comparison_report_path', 'n/a')}\n"
            f"[bold blue]Export Manifest:[/bold blue] {bundle.get('export_manifest_path', 'n/a')}\n"
            f"[bold blue]Export Content:[/bold blue] {bundle.get('export_content_path', 'n/a')}"
        )
    )


@app.command("benchmark-deliberation-campaigns")
def benchmark_deliberation_campaigns(
    topic: str,
    objective: str | None = None,
    mode: DeliberationMode = typer.Option(
        DeliberationMode.committee,
        "--mode",
        help="Deliberation mode shared by both benchmark runs.",
    ),
    participants: list[str] = typer.Option([], "--participant", help="Participant to include. Repeat to add more participants."),
    documents: list[str] = typer.Option([], "--document", help="Document or evidence snippet to ground the deliberation."),
    entities: list[str] = typer.Option([], "--entity", help="Entity payload as JSON or plain text. Repeat to add more entities."),
    interventions: list[str] = typer.Option([], "--intervention", help="Intervention or event injection to test during deliberation."),
    max_agents: int = typer.Option(6, "--max-agents", help="Maximum committee participants or base simulation agent count."),
    population_size: int | None = typer.Option(None, "--population-size", help="Population size for simulation or hybrid modes."),
    rounds: int = typer.Option(2, "--rounds", help="Committee discussion rounds or simulation rounds hint."),
    time_horizon: str = typer.Option("7d", "--time-horizon", help="Simulation horizon for simulation or hybrid modes."),
    config_path: str = typer.Option("config.yaml", "--config-path", help="Path to the swarm config."),
    benchmark_path: str = typer.Option(
        str(DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH),
        "--benchmark-path",
        help="Benchmark suite path for deliberation evaluation.",
    ),
    sample_count: int = typer.Option(3, "--sample-count", min=1, help="Number of comparable samples in each campaign."),
    stability_runs: int = typer.Option(1, "--stability-runs", min=1, help="Repeated runs inside each sample for stability scoring."),
    baseline_runtime: RuntimeBackend = typer.Option(
        RuntimeBackend.pydanticai,
        "--baseline-runtime",
        help="Runtime used for the baseline campaign.",
    ),
    candidate_runtime: RuntimeBackend = typer.Option(
        RuntimeBackend.legacy,
        "--candidate-runtime",
        help="Runtime used for the candidate campaign.",
    ),
    allow_fallback: bool = typer.Option(
        True,
        "--allow-fallback/--no-allow-fallback",
        help="Allow a legacy fallback if the preferred runtime is unavailable.",
    ),
    baseline_engine_preference: EnginePreference = typer.Option(
        EnginePreference.agentsociety,
        "--baseline-engine-preference",
        help="Engine used for the baseline campaign.",
    ),
    candidate_engine_preference: EnginePreference = typer.Option(
        EnginePreference.oasis,
        "--candidate-engine-preference",
        help="Engine used for the candidate campaign.",
    ),
    budget_max: float = typer.Option(10.0, "--budget-max", help="Budget cap for simulation-backed modes."),
    timeout_seconds: int = typer.Option(1800, "--timeout-seconds", help="Timeout for simulation-backed modes."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="AgentSociety backend mode: live, surrogate, or disabled."),
    campaign_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR),
        "--campaign-output-dir",
        help="Directory used to persist the baseline and candidate campaign reports.",
    ),
    comparison_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR),
        "--comparison-output-dir",
        help="Directory used to persist deliberation campaign comparison reports.",
    ),
    export_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR),
        "--export-output-dir",
        help="Directory used to persist deliberation campaign comparison exports.",
    ),
    benchmark_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR),
        "--benchmark-output-dir",
        help="Directory used to persist deliberation campaign benchmark reports.",
    ),
    format: str = typer.Option("markdown", "--format", help="Export format: markdown or json."),
    json_output: bool = typer.Option(False, "--json", help="Print the benchmark bundle as JSON."),
):
    """Run baseline and candidate campaigns, then compare, audit, and export the result."""
    bundle = _run_deliberation_campaign_benchmark(
        topic=topic,
        objective=objective,
        mode=mode,
        participants=[] if isinstance(participants, OptionInfo) else participants,
        documents=[] if isinstance(documents, OptionInfo) else documents,
        entities=_parse_entity_values([] if isinstance(entities, OptionInfo) else entities),
        interventions=[] if isinstance(interventions, OptionInfo) else interventions,
        max_agents=6 if isinstance(max_agents, OptionInfo) else max_agents,
        population_size=None if isinstance(population_size, OptionInfo) else population_size,
        rounds=2 if isinstance(rounds, OptionInfo) else rounds,
        time_horizon="7d" if isinstance(time_horizon, OptionInfo) else time_horizon,
        config_path="config.yaml" if isinstance(config_path, OptionInfo) else config_path,
        benchmark_path=str(DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH) if isinstance(benchmark_path, OptionInfo) else benchmark_path,
        sample_count=3 if isinstance(sample_count, OptionInfo) else sample_count,
        stability_runs=1 if isinstance(stability_runs, OptionInfo) else stability_runs,
        baseline_runtime=baseline_runtime,
        candidate_runtime=candidate_runtime,
        allow_fallback=allow_fallback,
        baseline_engine_preference=baseline_engine_preference,
        candidate_engine_preference=candidate_engine_preference,
        budget_max=10.0 if isinstance(budget_max, OptionInfo) else budget_max,
        timeout_seconds=1800 if isinstance(timeout_seconds, OptionInfo) else timeout_seconds,
        backend_mode=backend_mode,
        campaign_output_dir=campaign_output_dir,
        comparison_output_dir=comparison_output_dir,
        export_output_dir=export_output_dir,
        benchmark_output_dir=benchmark_output_dir,
        format=format,
    )
    benchmark_id = bundle.get("benchmark_id", "n/a")
    if json_output:
        _print_json(bundle)
        return
    console.print(
        Panel(
            f"[bold blue]Benchmark:[/bold blue] {benchmark_id}\n"
            f"[bold blue]Baseline Campaign:[/bold blue] {bundle.get('baseline_campaign_id', 'n/a')}\n"
            f"[bold blue]Candidate Campaign:[/bold blue] {bundle.get('candidate_campaign_id', 'n/a')}\n"
            f"[bold blue]Export ID:[/bold blue] {bundle.get('export_id', 'n/a')}\n"
            f"[bold blue]Benchmark Report:[/bold blue] {bundle.get('report_path', 'n/a')}\n"
            f"[bold blue]Comparison Report:[/bold blue] {bundle.get('comparison_report_path', 'n/a')}\n"
            f"[bold blue]Export Manifest:[/bold blue] {bundle.get('export_manifest_path', 'n/a')}\n"
            f"[bold blue]Export Content:[/bold blue] {bundle.get('export_content_path', 'n/a')}"
        )
    )


@app.command("benchmark-deliberation-campaign-matrix")
def benchmark_deliberation_campaign_matrix(
    topic: str,
    objective: str | None = None,
    mode: DeliberationMode = typer.Option(
        DeliberationMode.committee,
        "--mode",
        help="Deliberation mode shared by the baseline and every candidate run.",
    ),
    participants: list[str] = typer.Option([], "--participant", help="Participant to include. Repeat to add more participants."),
    documents: list[str] = typer.Option([], "--document", help="Document or evidence snippet to ground the deliberation."),
    entities: list[str] = typer.Option([], "--entity", help="Entity payload as JSON or plain text. Repeat to add more entities."),
    interventions: list[str] = typer.Option([], "--intervention", help="Intervention or event injection to test during deliberation."),
    max_agents: int = typer.Option(6, "--max-agents", help="Maximum committee participants or base simulation agent count."),
    population_size: int | None = typer.Option(None, "--population-size", help="Population size for simulation or hybrid modes."),
    rounds: int = typer.Option(2, "--rounds", help="Committee discussion rounds or simulation rounds hint."),
    time_horizon: str = typer.Option("7d", "--time-horizon", help="Simulation horizon for simulation or hybrid modes."),
    config_path: str = typer.Option("config.yaml", "--config-path", help="Path to the swarm config."),
    benchmark_path: str = typer.Option(
        str(DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH),
        "--benchmark-path",
        help="Benchmark suite path for deliberation evaluation.",
    ),
    sample_count: int = typer.Option(3, "--sample-count", min=1, help="Number of comparable samples in each campaign."),
    stability_runs: int = typer.Option(1, "--stability-runs", min=1, help="Repeated runs inside each sample for stability scoring."),
    baseline_runtime: RuntimeBackend = typer.Option(
        RuntimeBackend.pydanticai,
        "--baseline-runtime",
        help="Runtime used for the shared baseline campaign.",
    ),
    candidate_runtimes: list[RuntimeBackend] = typer.Option(
        [RuntimeBackend.legacy],
        "--candidate-runtime",
        help="Runtime used for each candidate campaign. Repeat to add more candidates.",
    ),
    allow_fallback: bool = typer.Option(
        True,
        "--allow-fallback/--no-allow-fallback",
        help="Allow a legacy fallback if the preferred runtime is unavailable.",
    ),
    baseline_engine_preference: EnginePreference = typer.Option(
        EnginePreference.agentsociety,
        "--baseline-engine-preference",
        help="Engine used for the shared baseline campaign.",
    ),
    candidate_engine_preferences: list[EnginePreference] = typer.Option(
        [EnginePreference.oasis],
        "--candidate-engine-preference",
        help="Engine used for each candidate campaign. Repeat to add more candidates.",
    ),
    baseline_campaign_id: str | None = typer.Option(
        None,
        "--baseline-campaign-id",
        help="Optional campaign ID for the shared baseline run.",
    ),
    candidate_campaign_ids: list[str] = typer.Option(
        [],
        "--candidate-campaign-id",
        help="Optional campaign ID for each candidate run. Repeat once per candidate.",
    ),
    matrix_id: str | None = typer.Option(
        None,
        "--matrix-id",
        help="Optional ID for the persisted matrix report.",
    ),
    budget_max: float = typer.Option(10.0, "--budget-max", help="Budget cap for simulation-backed modes."),
    timeout_seconds: int = typer.Option(1800, "--timeout-seconds", help="Timeout for simulation-backed modes."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="AgentSociety backend mode: live, surrogate, or disabled."),
    campaign_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR),
        "--campaign-output-dir",
        help="Directory used to persist the baseline and candidate campaign reports.",
    ),
    comparison_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR),
        "--comparison-output-dir",
        help="Directory used to persist deliberation campaign comparison reports.",
    ),
    export_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR),
        "--export-output-dir",
        help="Directory used to persist deliberation campaign comparison exports.",
    ),
    benchmark_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR),
        "--benchmark-output-dir",
        help="Directory used to persist deliberation campaign matrix benchmark reports.",
    ),
    format: str = typer.Option("markdown", "--format", help="Export format: markdown or json."),
    json_output: bool = typer.Option(False, "--json", help="Print the benchmark matrix as JSON."),
):
    """Run a shared baseline campaign against multiple candidates and persist a matrix report."""
    report = _run_deliberation_campaign_benchmark_matrix(
        topic=topic,
        objective=objective,
        mode=mode,
        participants=[] if isinstance(participants, OptionInfo) else participants,
        documents=[] if isinstance(documents, OptionInfo) else documents,
        entities=_parse_entity_values([] if isinstance(entities, OptionInfo) else entities),
        interventions=[] if isinstance(interventions, OptionInfo) else interventions,
        max_agents=6 if isinstance(max_agents, OptionInfo) else max_agents,
        population_size=None if isinstance(population_size, OptionInfo) else population_size,
        rounds=2 if isinstance(rounds, OptionInfo) else rounds,
        time_horizon="7d" if isinstance(time_horizon, OptionInfo) else time_horizon,
        config_path="config.yaml" if isinstance(config_path, OptionInfo) else config_path,
        benchmark_path=str(DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH) if isinstance(benchmark_path, OptionInfo) else benchmark_path,
        sample_count=3 if isinstance(sample_count, OptionInfo) else sample_count,
        stability_runs=1 if isinstance(stability_runs, OptionInfo) else stability_runs,
        baseline_runtime=baseline_runtime,
        candidate_runtimes=candidate_runtimes,
        allow_fallback=allow_fallback,
        baseline_engine_preference=baseline_engine_preference,
        candidate_engine_preferences=candidate_engine_preferences,
        baseline_campaign_id=baseline_campaign_id,
        candidate_campaign_ids=[] if isinstance(candidate_campaign_ids, OptionInfo) else candidate_campaign_ids,
        matrix_id=matrix_id,
        budget_max=10.0 if isinstance(budget_max, OptionInfo) else budget_max,
        timeout_seconds=1800 if isinstance(timeout_seconds, OptionInfo) else timeout_seconds,
        backend_mode=backend_mode,
        campaign_output_dir=campaign_output_dir,
        comparison_output_dir=comparison_output_dir,
        export_output_dir=export_output_dir,
        benchmark_output_dir=benchmark_output_dir,
        format=format,
    )
    if json_output:
        _print_json(report)
        return
    console.print(
        Panel(
            f"[bold blue]Matrix:[/bold blue] {report.get('matrix_id', 'n/a')}\n"
            f"[bold blue]Baseline Campaign:[/bold blue] {report.get('baseline_campaign_id', 'n/a')}\n"
            f"[bold blue]Benchmarks:[/bold blue] {len(report.get('benchmarks', []))}\n"
            f"[bold blue]Report:[/bold blue] {report.get('report_path', 'n/a')}"
        )
    )
    table = Table(title="Matrix Benchmarks", show_lines=False)
    table.add_column("Benchmark ID", style="cyan", no_wrap=True)
    table.add_column("Candidate", style="white")
    table.add_column("Comparable", style="green")
    table.add_column("Export", style="yellow")
    for benchmark in report.get("benchmarks", []) if isinstance(report.get("benchmarks", []), list) else []:
        comparison_bundle = benchmark.get("comparison_bundle", {}) if isinstance(benchmark.get("comparison_bundle", {}), dict) else {}
        comparison_report = (
            comparison_bundle.get("comparison_report", {})
            if isinstance(comparison_bundle.get("comparison_report", {}), dict)
            else {}
        )
        comparison_summary = (
            comparison_report.get("summary", {})
            if isinstance(comparison_report.get("summary", {}), dict)
            else {}
        )
        candidate_campaign = (
            benchmark.get("candidate_campaign", {})
            if isinstance(benchmark.get("candidate_campaign", {}), dict)
            else {}
        )
        table.add_row(
            str(benchmark.get("benchmark_id", "n/a")),
            str(benchmark.get("candidate_campaign_id", candidate_campaign.get("campaign_id", "n/a"))),
            "yes" if comparison_summary.get("comparable", True) else "no",
            str(benchmark.get("export_id", comparison_bundle.get("export", {}).get("export_id", "n/a"))),
        )
    console.print(table)


@app.command("read-deliberation-campaign-benchmark")
def read_deliberation_campaign_benchmark(
    benchmark_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the stored benchmark report as JSON."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign benchmark reports.",
    ),
):
    """Read a persisted deliberation campaign benchmark report by benchmark ID."""
    report = _load_deliberation_campaign_benchmark_report(benchmark_id, output_dir=output_dir)
    _print_deliberation_campaign_benchmark_report(report, as_json=json_output)


@app.command("read-deliberation-campaign-benchmark-matrix")
def read_deliberation_campaign_benchmark_matrix(
    matrix_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the stored benchmark matrix as JSON."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign benchmark matrix reports.",
    ),
):
    """Read a persisted deliberation campaign benchmark matrix report by matrix ID."""
    report = _load_deliberation_campaign_benchmark_matrix_report(matrix_id, output_dir=output_dir)
    _print_deliberation_campaign_benchmark_matrix_report(report, as_json=json_output)


@app.command("audit-deliberation-campaign-benchmark-matrix")
def audit_deliberation_campaign_benchmark_matrix(
    matrix_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the matrix benchmark audit as JSON."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign benchmark matrix reports.",
    ),
):
    """Audit a persisted deliberation campaign benchmark matrix report."""
    audit = _load_deliberation_campaign_benchmark_matrix_audit(
        matrix_id,
        output_dir=output_dir,
        include_markdown=not json_output,
    )
    _print_deliberation_campaign_benchmark_matrix_audit(audit, as_json=json_output)


@app.command("export-deliberation-campaign-benchmark-matrix")
def export_deliberation_campaign_benchmark_matrix(
    matrix_id: str,
    format: str = typer.Option("markdown", "--format", help="Export format: markdown or json."),
    output_path: str = typer.Option("", "--output-path", help="Optional explicit export destination."),
    json_output: bool = typer.Option(False, "--json", help="Print export metadata as JSON."),
    benchmark_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR),
        "--benchmark-output-dir",
        help="Directory containing persisted deliberation campaign benchmark matrix reports.",
    ),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted matrix benchmark exports.",
    ),
):
    """Export a persisted matrix benchmark audit as markdown or JSON."""
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        raise typer.BadParameter("format must be one of: markdown, json.")

    audit = _load_deliberation_campaign_benchmark_matrix_audit(
        matrix_id,
        output_dir=benchmark_output_dir,
        include_markdown=normalized_format == "markdown",
    )
    export = _materialize_deliberation_campaign_benchmark_matrix_export(
        audit,
        format=normalized_format,
        output_dir=output_dir,
        export_id=_benchmark_matrix_export_id(matrix_id, format=normalized_format),
    )
    export_payload = _matrix_benchmark_export_payload(export)
    target_path = (
        Path(output_path)
        if output_path
        else Path(export_payload.get("content_path", ""))
    )
    if output_path:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(str(export_payload.get("content", "")), encoding="utf-8")
    result_payload = {
        "export_id": export_payload.get("export_id"),
        "matrix_id": matrix_id,
        "format": normalized_format,
        "output_path": str(target_path) if str(target_path) else export_payload.get("content_path"),
        "content_path": export_payload.get("content_path"),
        "manifest_path": export_payload.get("manifest_path"),
        "report_path": export_payload.get("report_path"),
        "comparable": export_payload.get("comparable"),
        "mismatch_reasons": export_payload.get("mismatch_reasons", []),
        "best_candidate": export_payload.get("best_candidate"),
        "worst_candidate": export_payload.get("worst_candidate"),
    }
    if json_output:
        _print_json(result_payload)
        return

    console.print(
        Panel(
            f"[bold blue]Export ID:[/bold blue] {result_payload.get('export_id', 'n/a')}\n"
            f"[bold blue]Matrix ID:[/bold blue] {matrix_id}\n"
            f"[bold blue]Format:[/bold blue] {normalized_format}\n"
            f"[bold blue]Output Path:[/bold blue] {result_payload.get('output_path', 'n/a')}\n"
            f"[bold blue]Export Manifest:[/bold blue] {result_payload.get('manifest_path', 'n/a')}\n"
            f"[bold blue]Export Content:[/bold blue] {result_payload.get('content_path', 'n/a')}"
        )
    )


@app.command("read-deliberation-campaign-benchmark-matrix-export")
def read_deliberation_campaign_benchmark_matrix_export(
    export_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the stored matrix benchmark export as JSON."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted matrix benchmark exports.",
    ),
):
    """Read a persisted matrix benchmark export by export ID."""
    export = _load_deliberation_campaign_benchmark_matrix_export(export_id, output_dir=output_dir)
    _print_deliberation_campaign_benchmark_matrix_export(export, as_json=json_output)


@app.command("list-deliberation-campaign-benchmark-matrix-exports")
def list_deliberation_campaign_benchmark_matrix_exports(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum number of persisted matrix benchmark exports to list."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted matrix benchmark exports.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the matrix benchmark export list as JSON."),
):
    """List persisted matrix benchmark exports."""
    exports = _collect_deliberation_campaign_benchmark_matrix_exports(limit=limit, output_dir=output_dir)
    _print_deliberation_campaign_benchmark_matrix_export_list(
        exports,
        output_dir=output_dir,
        limit=limit,
        as_json=json_output,
    )


@app.command("compare-deliberation-campaign-benchmark-matrix-exports")
def compare_deliberation_campaign_benchmark_matrix_exports(
    export_ids: list[str] = typer.Argument(
        [],
        metavar="EXPORT_ID",
        help="Two or more persisted matrix benchmark export IDs to compare, or use --latest.",
    ),
    latest: int | None = typer.Option(
        None,
        "--latest",
        min=2,
        help="Compare the N most recent persisted matrix benchmark exports.",
    ),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted matrix benchmark exports.",
    ),
    persist: bool = typer.Option(
        True,
        "--persist/--no-persist",
        help="Persist the matrix benchmark export comparison report.",
    ),
    comparison_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR),
        "--comparison-output-dir",
        help="Directory used to persist matrix benchmark export comparison reports.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the export comparison as JSON."),
):
    """Compare persisted matrix benchmark exports."""
    if latest is not None and export_ids:
        raise typer.BadParameter("Use either explicit export IDs or --latest, not both.")
    if latest is None and len(export_ids) < 2:
        raise typer.BadParameter("Provide at least two matrix benchmark export IDs, or use --latest.")

    helper = getattr(
        deliberation_campaign_core,
        "compare_deliberation_campaign_matrix_benchmark_exports",
        None,
    )
    if not callable(helper):
        raise typer.BadParameter("Matrix benchmark export comparison is not available in the current core.")
    comparison_report = helper(
        export_ids=None if latest is not None else export_ids,
        latest=latest,
        output_dir=output_dir,
        persist=persist,
        comparison_output_dir=comparison_output_dir,
    )
    _print_deliberation_campaign_benchmark_matrix_export_comparison(
        comparison_report,
        as_json=json_output,
    )


@app.command("read-deliberation-campaign-benchmark-matrix-export-comparison")
def read_deliberation_campaign_benchmark_matrix_export_comparison(
    comparison_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the stored export comparison as JSON."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted matrix benchmark export comparison reports.",
    ),
):
    """Read a persisted matrix benchmark export comparison report by comparison ID."""
    report = _load_deliberation_campaign_benchmark_matrix_export_comparison_report(
        comparison_id,
        output_dir=output_dir,
    )
    _print_deliberation_campaign_benchmark_matrix_export_comparison(report, as_json=json_output)


@app.command("list-deliberation-campaign-benchmark-matrix-export-comparisons")
def list_deliberation_campaign_benchmark_matrix_export_comparisons(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum number of persisted export comparisons to list."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted matrix benchmark export comparison reports.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the export comparison list as JSON."),
):
    """List persisted matrix benchmark export comparison reports."""
    reports = _collect_deliberation_campaign_benchmark_matrix_export_comparison_reports(
        limit=limit,
        output_dir=output_dir,
    )
    _print_deliberation_campaign_benchmark_matrix_export_comparison_list(
        reports,
        output_dir=output_dir,
        limit=limit,
        as_json=json_output,
    )


@app.command("compare-deliberation-campaign-benchmark-matrix-exports-audit-export")
def compare_deliberation_campaign_benchmark_matrix_exports_audit_export(
    export_ids: list[str] = typer.Argument(
        [],
        metavar="EXPORT_ID",
        help="Two or more persisted matrix benchmark export IDs to compare, or use --latest.",
    ),
    latest: int | None = typer.Option(
        None,
        "--latest",
        min=2,
        help="Compare the N most recent persisted matrix benchmark exports.",
    ),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted matrix benchmark exports.",
    ),
    comparison_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR),
        "--comparison-output-dir",
        help="Directory used to persist matrix benchmark export comparison reports.",
    ),
    export_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR),
        "--export-output-dir",
        help="Directory used to persist matrix benchmark export comparison exports.",
    ),
    format: str = typer.Option("markdown", "--format", help="Export format: markdown or json."),
    json_output: bool = typer.Option(False, "--json", help="Print the workflow bundle as JSON."),
):
    """Compare persisted matrix benchmark exports, build the audit, and persist the final export."""
    if latest is not None and export_ids:
        raise typer.BadParameter("Use either explicit export IDs or --latest, not both.")
    if latest is None and len(export_ids) < 2:
        raise typer.BadParameter("Provide at least two matrix benchmark export IDs, or use --latest.")

    helper = getattr(
        deliberation_campaign_core,
        "compare_deliberation_campaign_matrix_benchmark_export_comparison_bundle",
        None,
    )
    if not callable(helper):
        raise typer.BadParameter("Matrix benchmark export comparison is not available in the current core.")

    bundle_result = helper(
        export_ids=None if latest is not None else export_ids,
        latest=latest,
        output_dir=output_dir,
        persist=True,
        comparison_output_dir=comparison_output_dir,
        export_output_dir=export_output_dir,
        format=format,
    )
    bundle_payload = (
        bundle_result.model_dump(mode="json")
        if hasattr(bundle_result, "model_dump")
        else dict(bundle_result)
    )
    comparison_payload = bundle_payload.get("comparison_report", {})
    audit_payload = bundle_payload.get("audit", {})
    export_payload = bundle_payload.get("export", {})
    comparison_id = str(comparison_payload.get("comparison_id", "n/a"))
    bundle = {
        "comparison_report": comparison_payload,
        "audit": audit_payload,
        "export": export_payload,
        "comparison_id": comparison_id,
        "export_id": export_payload.get("export_id"),
        "comparison_report_path": comparison_payload.get("report_path"),
        "audit_report_path": audit_payload.get("report_path"),
        "export_manifest_path": export_payload.get("manifest_path"),
        "export_content_path": export_payload.get("content_path"),
    }
    if json_output:
        _print_json(bundle)
        return
    console.print(
        Panel(
            f"[bold blue]Comparison ID:[/bold blue] {comparison_id}\n"
            f"[bold blue]Export ID:[/bold blue] {bundle.get('export_id', 'n/a')}\n"
            f"[bold blue]Comparison Report:[/bold blue] {bundle.get('comparison_report_path', 'n/a')}\n"
            f"[bold blue]Audit Report:[/bold blue] {bundle.get('audit_report_path', 'n/a')}\n"
            f"[bold blue]Export Manifest:[/bold blue] {bundle.get('export_manifest_path', 'n/a')}\n"
            f"[bold blue]Export Content:[/bold blue] {bundle.get('export_content_path', 'n/a')}"
        )
    )


@app.command("audit-deliberation-campaign-benchmark-matrix-export-comparison")
def audit_deliberation_campaign_benchmark_matrix_export_comparison(
    comparison_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the export comparison audit as JSON."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted matrix benchmark export comparison reports.",
    ),
):
    """Audit a persisted matrix benchmark export comparison report."""
    audit = _load_deliberation_campaign_benchmark_matrix_export_comparison_audit(
        comparison_id,
        output_dir=output_dir,
        include_markdown=not json_output,
    )
    _print_deliberation_campaign_benchmark_matrix_export_comparison_audit(audit, as_json=json_output)


@app.command("export-deliberation-campaign-benchmark-matrix-export-comparison")
def export_deliberation_campaign_benchmark_matrix_export_comparison(
    comparison_id: str,
    format: str = typer.Option("markdown", "--format", help="Export format: markdown or json."),
    output_path: str = typer.Option("", "--output-path", help="Optional explicit export destination."),
    json_output: bool = typer.Option(False, "--json", help="Print export metadata as JSON."),
    comparison_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR),
        "--comparison-output-dir",
        help="Directory containing persisted matrix benchmark export comparison reports.",
    ),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted matrix benchmark export comparison exports.",
    ),
):
    """Export a persisted matrix benchmark export comparison audit as markdown or JSON."""
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        raise typer.BadParameter("format must be one of: markdown, json.")

    audit = _load_deliberation_campaign_benchmark_matrix_export_comparison_audit(
        comparison_id,
        output_dir=comparison_output_dir,
        include_markdown=normalized_format == "markdown",
    )
    helper = getattr(
        deliberation_campaign_core,
        "materialize_deliberation_campaign_matrix_benchmark_export_comparison_export",
        None,
    )
    if not callable(helper):
        raise typer.BadParameter("Matrix benchmark export comparison export is not available in the current core.")
    export = helper(
        audit,
        format=normalized_format,
        output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR,
        export_id=f"{comparison_id}__{normalized_format}",
    )
    export_payload = _matrix_benchmark_export_comparison_export_payload(export)
    target_path = (
        Path(output_path)
        if output_path
        else Path(
            export_payload.get("content_path")
            or (
                Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR)
                / str(export_payload.get("export_id", f"{comparison_id}__{normalized_format}"))
                / ("content.md" if normalized_format == "markdown" else "content.json")
            )
        )
    )
    if output_path:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(str(export_payload.get("content", "")), encoding="utf-8")

    result_payload = {
        "export_id": export_payload.get("export_id"),
        "comparison_id": comparison_id,
        "format": normalized_format,
        "output_path": str(target_path),
        "content_path": export_payload.get("content_path"),
        "manifest_path": export_payload.get("manifest_path"),
        "comparison_report_path": export_payload.get("comparison_report_path"),
        "comparable": export_payload.get("comparable"),
        "mismatch_reasons": export_payload.get("mismatch_reasons", []),
    }
    if json_output:
        _print_json(result_payload)
        return
    console.print(
        Panel(
            f"[bold blue]Export ID:[/bold blue] {result_payload.get('export_id', 'n/a')}\n"
            f"[bold blue]Comparison ID:[/bold blue] {comparison_id}\n"
            f"[bold blue]Format:[/bold blue] {normalized_format}\n"
            f"[bold blue]Output Path:[/bold blue] {result_payload.get('output_path', 'n/a')}\n"
            f"[bold blue]Export Manifest:[/bold blue] {result_payload.get('manifest_path', 'n/a')}\n"
            f"[bold blue]Export Content:[/bold blue] {result_payload.get('content_path', 'n/a')}"
        )
    )


@app.command("read-deliberation-campaign-benchmark-matrix-export-comparison-export")
def read_deliberation_campaign_benchmark_matrix_export_comparison_export(
    export_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the stored export comparison export as JSON."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted matrix benchmark export comparison exports.",
    ),
):
    """Read a persisted matrix benchmark export comparison export by export ID."""
    export = _load_deliberation_campaign_benchmark_matrix_export_comparison_export(
        export_id,
        output_dir=output_dir,
    )
    _print_deliberation_campaign_benchmark_matrix_export_comparison_export(export, as_json=json_output)


@app.command("list-deliberation-campaign-benchmark-matrix-export-comparison-exports")
def list_deliberation_campaign_benchmark_matrix_export_comparison_exports(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum number of persisted export comparison exports to list."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted matrix benchmark export comparison exports.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the export comparison export list as JSON."),
):
    """List persisted matrix benchmark export comparison exports."""
    exports = _collect_deliberation_campaign_benchmark_matrix_export_comparison_exports(
        limit=limit,
        output_dir=output_dir,
    )
    _print_deliberation_campaign_benchmark_matrix_export_comparison_export_list(
        exports,
        output_dir=output_dir,
        limit=limit,
        as_json=json_output,
    )


@app.command("compare-deliberation-campaign-benchmark-matrices")
def compare_deliberation_campaign_benchmark_matrices(
    matrix_ids: list[str] = typer.Argument(
        [],
        metavar="MATRIX_ID",
        help="Two persisted matrix benchmark IDs to compare, or use --latest to compare the newest pair.",
    ),
    latest: bool = typer.Option(False, "--latest", help="Compare the two most recent persisted matrix benchmarks."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign benchmark matrix reports.",
    ),
    persist: bool = typer.Option(
        True,
        "--persist/--no-persist",
        help="Persist the matrix benchmark comparison report under the comparison output directory.",
    ),
    comparison_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR),
        "--comparison-output-dir",
        help="Directory used to persist matrix benchmark comparison reports.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the matrix benchmark comparison as JSON."),
):
    """Compare two persisted deliberation campaign benchmark matrices."""
    if latest and matrix_ids:
        raise typer.BadParameter("Use either explicit matrix benchmark IDs or --latest, not both.")
    comparison_report = _compare_deliberation_campaign_benchmark_matrices(
        matrix_ids=matrix_ids,
        latest=latest,
        output_dir=output_dir,
        persist=persist,
        comparison_output_dir=comparison_output_dir,
    )
    _print_deliberation_campaign_benchmark_matrix_comparison(
        comparison_report,
        as_json=json_output,
    )


@app.command("read-deliberation-campaign-benchmark-matrix-comparison")
def read_deliberation_campaign_benchmark_matrix_comparison(
    comparison_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the stored matrix comparison as JSON."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign benchmark matrix comparison reports.",
    ),
):
    """Read a persisted deliberation campaign benchmark matrix comparison report by comparison ID."""
    report = _load_deliberation_campaign_benchmark_matrix_comparison_report(
        comparison_id,
        output_dir=output_dir,
    )
    _print_deliberation_campaign_benchmark_matrix_comparison(report, as_json=json_output)


@app.command("list-deliberation-campaign-benchmark-matrix-comparisons")
def list_deliberation_campaign_benchmark_matrix_comparisons(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum number of persisted matrix comparisons to list."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign benchmark matrix comparison reports.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the matrix comparison list as JSON."),
):
    """List persisted deliberation campaign benchmark matrix comparison reports."""
    reports = _collect_deliberation_campaign_benchmark_matrix_comparison_reports(
        limit=limit,
        output_dir=output_dir,
    )
    _print_deliberation_campaign_benchmark_matrix_comparison_list(
        reports,
        output_dir=output_dir,
        limit=limit,
        as_json=json_output,
    )


@app.command("compare-deliberation-campaign-benchmark-matrices-audit-export")
def compare_deliberation_campaign_benchmark_matrices_audit_export(
    matrix_ids: list[str] = typer.Argument(
        [],
        metavar="MATRIX_ID",
        help="Two persisted matrix benchmark IDs to compare, or use --latest to compare the newest pair.",
    ),
    latest: bool = typer.Option(False, "--latest", help="Compare the two most recent persisted matrix benchmarks."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign benchmark matrix reports.",
    ),
    comparison_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR),
        "--comparison-output-dir",
        help="Directory used to persist matrix benchmark comparison reports.",
    ),
    export_output_dir: str = typer.Option(
        str(CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR),
        "--export-output-dir",
        help="Directory used to persist matrix benchmark comparison exports.",
    ),
    format: str = typer.Option("markdown", "--format", help="Export format: markdown or json."),
    json_output: bool = typer.Option(False, "--json", help="Print the workflow bundle as JSON."),
):
    """Compare two persisted matrix benchmarks, build the audit, and persist the final export."""
    if latest and matrix_ids:
        raise typer.BadParameter("Use either explicit matrix benchmark IDs or --latest, not both.")

    bundle_helper = getattr(
        deliberation_campaign_core,
        "compare_deliberation_campaign_matrix_benchmark_comparison_bundle",
        None,
    )
    if callable(bundle_helper):
        if latest:
            bundle_result = bundle_helper(
                latest=2,
                output_dir=output_dir,
                persist=True,
                comparison_output_dir=comparison_output_dir,
                export_output_dir=export_output_dir,
                format=format,
            )
        else:
            if len(matrix_ids) != 2:
                raise typer.BadParameter("Provide exactly two matrix benchmark IDs, or use --latest.")
            bundle_result = bundle_helper(
                benchmark_ids=matrix_ids,
                output_dir=output_dir,
                persist=True,
                comparison_output_dir=comparison_output_dir,
                export_output_dir=export_output_dir,
                format=format,
            )
        bundle_payload = (
            bundle_result.model_dump(mode="json")
            if hasattr(bundle_result, "model_dump")
            else dict(bundle_result)
        )
        comparison_payload = bundle_payload.get("comparison_report", {})
        audit_payload = bundle_payload.get("audit", {})
        export_payload = bundle_payload.get("export", {})
        comparison_id = str(comparison_payload.get("comparison_id", "n/a"))
    else:
        comparison_report = _compare_deliberation_campaign_benchmark_matrices(
            matrix_ids=matrix_ids,
            latest=latest,
            output_dir=output_dir,
            persist=True,
            comparison_output_dir=comparison_output_dir,
        )
        comparison_payload = _matrix_benchmark_comparison_report_payload(comparison_report)
        comparison_id = str(comparison_payload.get("comparison_id", "n/a"))
        audit = _load_deliberation_campaign_benchmark_matrix_comparison_audit(
            comparison_id,
            output_dir=comparison_output_dir,
            include_markdown=True,
        )
        export = _materialize_deliberation_campaign_benchmark_matrix_comparison_export(
            comparison_id,
            audit,
            output_dir=export_output_dir,
            format=format,
        )
        audit_payload = _matrix_benchmark_comparison_audit_payload(audit)
        export_payload = _matrix_benchmark_comparison_export_payload(export)

    bundle = {
        "comparison_report": comparison_payload,
        "audit": audit_payload,
        "export": export_payload,
        "comparison_id": comparison_id,
        "export_id": export_payload.get("export_id"),
        "comparison_report_path": comparison_payload.get("report_path"),
        "audit_report_path": audit_payload.get("report_path"),
        "export_manifest_path": export_payload.get("manifest_path"),
        "export_content_path": export_payload.get("content_path"),
    }
    if json_output:
        _print_json(bundle)
        return
    console.print(
        Panel(
            f"[bold blue]Comparison ID:[/bold blue] {comparison_id}\n"
            f"[bold blue]Export ID:[/bold blue] {bundle.get('export_id', 'n/a')}\n"
            f"[bold blue]Comparison Report:[/bold blue] {bundle.get('comparison_report_path', 'n/a')}\n"
            f"[bold blue]Audit Report:[/bold blue] {bundle.get('audit_report_path', 'n/a')}\n"
            f"[bold blue]Export Manifest:[/bold blue] {bundle.get('export_manifest_path', 'n/a')}\n"
            f"[bold blue]Export Content:[/bold blue] {bundle.get('export_content_path', 'n/a')}"
        )
    )


@app.command("audit-deliberation-campaign-benchmark-matrix-comparison")
def audit_deliberation_campaign_benchmark_matrix_comparison(
    comparison_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the matrix comparison audit as JSON."),
    output_dir: str = typer.Option(
        str(CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign benchmark matrix comparison reports.",
    ),
):
    """Audit a persisted deliberation campaign benchmark matrix comparison report."""
    audit = _load_deliberation_campaign_benchmark_matrix_comparison_audit(
        comparison_id,
        output_dir=output_dir,
        include_markdown=not json_output,
    )
    _print_deliberation_campaign_benchmark_matrix_comparison_audit(audit, as_json=json_output)


@app.command("export-deliberation-campaign-benchmark-matrix-comparison")
def export_deliberation_campaign_benchmark_matrix_comparison(
    comparison_id: str,
    format: str = typer.Option("markdown", "--format", help="Export format: markdown or json."),
    output_path: str = typer.Option("", "--output-path", help="Optional explicit export destination."),
    json_output: bool = typer.Option(False, "--json", help="Print export metadata as JSON."),
    comparison_output_dir: str = typer.Option(
        str(CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR),
        "--comparison-output-dir",
        help="Directory containing persisted deliberation campaign benchmark matrix comparison reports.",
    ),
    output_dir: str = typer.Option(
        str(CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted matrix benchmark comparison exports.",
    ),
):
    """Export a persisted matrix benchmark comparison audit as markdown or JSON."""
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        raise typer.BadParameter("format must be one of: markdown, json.")

    audit = _load_deliberation_campaign_benchmark_matrix_comparison_audit(
        comparison_id,
        output_dir=comparison_output_dir,
        include_markdown=normalized_format == "markdown",
    )
    helper = getattr(
        deliberation_campaign_core,
        "materialize_deliberation_campaign_matrix_benchmark_comparison_export",
        None,
    )
    if callable(helper):
        export = helper(
            audit,
            format=normalized_format,
            output_dir=output_dir or CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR,
            export_id=_matrix_benchmark_comparison_export_id(comparison_id, format=normalized_format),
        )
    else:
        export = _materialize_deliberation_campaign_benchmark_matrix_comparison_export(
            comparison_id,
            audit,
            output_dir=output_dir,
            format=normalized_format,
        )

    export_payload = _matrix_benchmark_comparison_export_payload(export)
    target_path = (
        Path(output_path)
        if output_path
        else Path(
            export_payload.get("content_path")
            or (
                Path(output_dir or CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR)
                / str(export_payload.get("export_id", _matrix_benchmark_comparison_export_id(comparison_id, format=normalized_format)))
                / ("content.md" if normalized_format == "markdown" else "content.json")
            )
        )
    )
    if output_path:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(str(export_payload.get("content", "")), encoding="utf-8")

    result_payload = {
        "export_id": export_payload.get("export_id"),
        "comparison_id": comparison_id,
        "format": normalized_format,
        "output_path": str(target_path),
        "content_path": export_payload.get("content_path"),
        "manifest_path": export_payload.get("manifest_path"),
        "comparison_report_path": export_payload.get("comparison_report_path"),
        "comparable": export_payload.get("comparable"),
        "mismatch_reasons": export_payload.get("mismatch_reasons", []),
    }
    if json_output:
        _print_json(result_payload)
        return

    console.print(
        Panel(
            f"[bold blue]Export ID:[/bold blue] {result_payload.get('export_id', 'n/a')}\n"
            f"[bold blue]Comparison ID:[/bold blue] {comparison_id}\n"
            f"[bold blue]Format:[/bold blue] {normalized_format}\n"
            f"[bold blue]Output Path:[/bold blue] {result_payload.get('output_path', 'n/a')}\n"
            f"[bold blue]Export Manifest:[/bold blue] {result_payload.get('manifest_path', 'n/a')}\n"
            f"[bold blue]Export Content:[/bold blue] {result_payload.get('content_path', 'n/a')}"
        )
    )


@app.command("read-deliberation-campaign-benchmark-matrix-comparison-export")
def read_deliberation_campaign_benchmark_matrix_comparison_export(
    export_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the stored matrix comparison export as JSON."),
    output_dir: str = typer.Option(
        str(CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted matrix benchmark comparison exports.",
    ),
):
    """Read a persisted matrix benchmark comparison export by export ID."""
    export = _load_deliberation_campaign_benchmark_matrix_comparison_export(export_id, output_dir=output_dir)
    _print_deliberation_campaign_benchmark_matrix_comparison_export(export, as_json=json_output)


@app.command("list-deliberation-campaign-benchmark-matrix-comparison-exports")
def list_deliberation_campaign_benchmark_matrix_comparison_exports(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum number of persisted matrix comparison exports to list."),
    output_dir: str = typer.Option(
        str(CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted matrix benchmark comparison exports.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the matrix comparison export list as JSON."),
):
    """List persisted matrix benchmark comparison exports."""
    exports = _collect_deliberation_campaign_benchmark_matrix_comparison_exports(limit=limit, output_dir=output_dir)
    _print_deliberation_campaign_benchmark_matrix_comparison_export_list(
        exports,
        output_dir=output_dir,
        limit=limit,
        as_json=json_output,
    )


@app.command("list-deliberation-campaign-benchmarks")
def list_deliberation_campaign_benchmarks(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum number of persisted benchmark reports to list."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign benchmark reports.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the benchmark list as JSON."),
):
    """List persisted deliberation campaign benchmark reports."""
    reports = _collect_deliberation_campaign_benchmark_reports(limit=limit, output_dir=output_dir)
    _print_deliberation_campaign_benchmark_list(
        reports,
        output_dir=output_dir,
        limit=limit,
        as_json=json_output,
    )


@app.command("list-deliberation-campaign-benchmark-matrices")
def list_deliberation_campaign_benchmark_matrices(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum number of persisted benchmark matrices to list."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign benchmark matrix reports.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the benchmark matrix list as JSON."),
):
    """List persisted deliberation campaign benchmark matrix reports."""
    reports = _collect_deliberation_campaign_benchmark_matrix_reports(limit=limit, output_dir=output_dir)
    _print_deliberation_campaign_benchmark_matrix_list(
        reports,
        output_dir=output_dir,
        limit=limit,
        as_json=json_output,
    )


@app.command("deliberation-campaign-index")
def deliberation_campaign_index(
    limit: int = typer.Option(10, "--limit", min=1, help="Maximum number of recent artifacts to show per category."),
    campaign_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR),
        "--campaign-output-dir",
        help="Directory containing persisted deliberation campaign reports.",
    ),
    comparison_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR),
        "--comparison-output-dir",
        help="Directory containing persisted deliberation campaign comparison reports.",
    ),
    export_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR),
        "--export-output-dir",
        help="Directory containing persisted deliberation campaign comparison exports.",
    ),
    benchmark_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR),
        "--benchmark-output-dir",
        help="Directory containing persisted deliberation campaign benchmark reports.",
    ),
    matrix_benchmark_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR),
        "--matrix-benchmark-output-dir",
        help="Directory containing persisted deliberation campaign matrix benchmark reports.",
    ),
    matrix_benchmark_export_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR),
        "--matrix-benchmark-export-output-dir",
        help="Directory containing persisted deliberation campaign matrix benchmark exports.",
    ),
    matrix_benchmark_comparison_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR),
        "--matrix-benchmark-comparison-output-dir",
        help="Directory containing persisted deliberation campaign benchmark matrix comparison reports.",
    ),
    matrix_benchmark_comparison_export_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR),
        "--matrix-benchmark-comparison-export-output-dir",
        help="Directory containing persisted deliberation campaign benchmark matrix comparison exports.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the artifact index as JSON."),
):
    """Show a compact index of campaign, comparison, export, benchmark, matrix benchmark, matrix export, matrix comparison, and matrix comparison export artifacts."""
    payload = _deliberation_campaign_index_payload(
        limit=limit,
        campaign_output_dir=campaign_output_dir,
        comparison_output_dir=comparison_output_dir,
        export_output_dir=export_output_dir,
        benchmark_output_dir=benchmark_output_dir,
        matrix_benchmark_output_dir=matrix_benchmark_output_dir,
        matrix_benchmark_export_output_dir=matrix_benchmark_export_output_dir,
        matrix_benchmark_comparison_output_dir=matrix_benchmark_comparison_output_dir,
        matrix_benchmark_comparison_export_output_dir=matrix_benchmark_comparison_export_output_dir,
    )
    _print_deliberation_campaign_index(payload, as_json=json_output)


@app.command("deliberation-campaign-dashboard")
def deliberation_campaign_dashboard(
    kind: list[str] = typer.Option(
        [],
        "--kind",
        help="Artifact kind to include: campaign, comparison, export, benchmark, matrix_benchmark, matrix_benchmark_export, matrix_benchmark_comparison, or matrix_benchmark_comparison_export. Repeat to include more.",
    ),
    limit: int = typer.Option(10, "--limit", min=1, help="Maximum number of dashboard rows to show."),
    sort_by: str = typer.Option(
        "created_at",
        "--sort-by",
        help="Sort rows by created_at, kind, status, or comparable.",
    ),
    campaign_status: DeliberationCampaignStatus | None = typer.Option(
        None,
        "--campaign-status",
        help="Optional status filter for campaign rows.",
    ),
    comparable_only: bool = typer.Option(
        False,
        "--comparable-only",
        help="Only keep rows marked comparable.",
    ),
    campaign_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR),
        "--campaign-output-dir",
        help="Directory containing persisted deliberation campaign reports.",
    ),
    comparison_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR),
        "--comparison-output-dir",
        help="Directory containing persisted deliberation campaign comparison reports.",
    ),
    export_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR),
        "--export-output-dir",
        help="Directory containing persisted deliberation campaign comparison exports.",
    ),
    benchmark_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR),
        "--benchmark-output-dir",
        help="Directory containing persisted deliberation campaign benchmark reports.",
    ),
    matrix_benchmark_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR),
        "--matrix-benchmark-output-dir",
        help="Directory containing persisted deliberation campaign matrix benchmark reports.",
    ),
    matrix_benchmark_export_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR),
        "--matrix-benchmark-export-output-dir",
        help="Directory containing persisted deliberation campaign matrix benchmark exports.",
    ),
    matrix_benchmark_comparison_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR),
        "--matrix-benchmark-comparison-output-dir",
        help="Directory containing persisted deliberation campaign benchmark matrix comparison reports.",
    ),
    matrix_benchmark_comparison_export_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR),
        "--matrix-benchmark-comparison-export-output-dir",
        help="Directory containing persisted deliberation campaign benchmark matrix comparison exports.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the dashboard as JSON."),
):
    """Render a synthetic dashboard across persisted deliberation artifacts."""
    payload = _deliberation_campaign_dashboard_payload(
        kinds=kind,
        limit=limit,
        sort_by=sort_by,
        campaign_status=campaign_status,
        comparable_only=comparable_only,
        campaign_output_dir=campaign_output_dir,
        comparison_output_dir=comparison_output_dir,
        export_output_dir=export_output_dir,
        benchmark_output_dir=benchmark_output_dir,
        matrix_benchmark_output_dir=matrix_benchmark_output_dir,
        matrix_benchmark_export_output_dir=matrix_benchmark_export_output_dir,
        matrix_benchmark_comparison_output_dir=matrix_benchmark_comparison_output_dir,
        matrix_benchmark_comparison_export_output_dir=matrix_benchmark_comparison_export_output_dir,
    )
    _print_deliberation_campaign_dashboard(payload, as_json=json_output)


@app.command("read-deliberation-campaign-comparison")
def read_deliberation_campaign_comparison(
    comparison_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the stored comparison report as JSON."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign comparison reports.",
    ),
):
    """Read a persisted deliberation campaign comparison report by comparison ID."""
    report = _load_deliberation_campaign_comparison_report(comparison_id, output_dir=output_dir)
    _print_deliberation_campaign_comparison(report, output_dir=output_dir, as_json=json_output)


@app.command("list-deliberation-campaign-comparisons")
def list_deliberation_campaign_comparisons(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum number of persisted comparison reports to list."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign comparison reports.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the comparison list as JSON."),
):
    """List persisted deliberation campaign comparison reports."""
    reports = _collect_deliberation_campaign_comparison_reports(limit=limit, output_dir=output_dir)
    _print_deliberation_campaign_comparison_list(
        reports,
        output_dir=output_dir,
        limit=limit,
        as_json=json_output,
    )


@app.command("audit-deliberation-campaign-comparison")
def audit_deliberation_campaign_comparison(
    comparison_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the comparison audit as JSON."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign comparison reports.",
    ),
):
    """Audit a persisted deliberation campaign comparison report."""
    audit = _load_deliberation_campaign_comparison_audit(
        comparison_id,
        output_dir=output_dir,
        include_markdown=not json_output,
    )
    _print_deliberation_campaign_comparison_audit(audit, as_json=json_output)


@app.command("export-deliberation-campaign-comparison")
def export_deliberation_campaign_comparison(
    comparison_id: str,
    format: str = typer.Option("markdown", "--format", help="Export format: markdown or json."),
    output_path: str = typer.Option("", "--output-path", help="Optional explicit export destination."),
    json_output: bool = typer.Option(False, "--json", help="Print export metadata as JSON."),
    comparison_output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR),
        "--comparison-output-dir",
        help="Directory containing persisted deliberation campaign comparison reports.",
    ),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign comparison exports.",
    ),
):
    """Export a persisted deliberation campaign comparison audit as markdown or JSON."""
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        raise typer.BadParameter("format must be one of: markdown, json.")

    audit = _load_deliberation_campaign_comparison_audit(
        comparison_id,
        output_dir=comparison_output_dir,
        include_markdown=normalized_format == "markdown",
    )
    materialize_helper = getattr(
        deliberation_campaign_core,
        "materialize_deliberation_campaign_comparison_export",
        None,
    )
    if callable(materialize_helper):
        export = materialize_helper(
            audit,
            format=normalized_format,
            output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR,
            export_id=_comparison_export_id(comparison_id, format=normalized_format),
        )
    else:
        audit_payload = _comparison_audit_payload(audit)
        export = {
            "export_id": _comparison_export_id(comparison_id, format=normalized_format),
            "comparison_id": comparison_id,
            "format": normalized_format,
            "content_path": "",
            "manifest_path": "",
            "report_path": audit_payload.get("report_path"),
            "comparable": audit_payload.get("comparable"),
            "mismatch_reasons": audit_payload.get("mismatch_reasons", []),
            "content": (
                audit_payload.get("markdown")
                if normalized_format == "markdown"
                else json.dumps(audit_payload, indent=2, sort_keys=True)
            ),
        }

    export_payload = _comparison_export_payload(export)
    target_path = (
        Path(output_path)
        if output_path
        else Path(
            export_payload.get("content_path")
            or (
                Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR)
                / str(export_payload.get("export_id", _comparison_export_id(comparison_id, format=normalized_format)))
                / ("content.md" if normalized_format == "markdown" else "content.json")
            )
        )
    )
    if output_path:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(str(export_payload.get("content", "")), encoding="utf-8")

    result_payload = {
        "export_id": export_payload.get("export_id"),
        "comparison_id": comparison_id,
        "format": normalized_format,
        "output_path": str(target_path),
        "content_path": export_payload.get("content_path"),
        "manifest_path": export_payload.get("manifest_path"),
        "report_path": export_payload.get("comparison_report_path") or export_payload.get("report_path"),
        "comparable": export_payload.get("comparable"),
        "mismatch_reasons": export_payload.get("mismatch_reasons", []),
    }
    if json_output:
        _print_json(result_payload)
        return
    console.print(
        Panel(
            f"[bold blue]Comparison ID:[/bold blue] {comparison_id}\n"
            f"[bold blue]Export ID:[/bold blue] {result_payload.get('export_id', 'n/a')}\n"
            f"[bold blue]Format:[/bold blue] {normalized_format}\n"
            f"[bold blue]Output:[/bold blue] {target_path}\n"
            f"[bold blue]Comparable:[/bold blue] {'yes' if export_payload.get('comparable') else 'no'}\n"
            f"[bold blue]Mismatch:[/bold blue] {', '.join(export_payload.get('mismatch_reasons', [])) or 'none'}"
        )
    )


@app.command("read-deliberation-campaign-comparison-export")
def read_deliberation_campaign_comparison_export(
    comparison_id: str,
    format: str = typer.Option("markdown", "--format", help="Export format to read: markdown or json."),
    json_output: bool = typer.Option(False, "--json", help="Print the export metadata and content as JSON."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign comparison exports.",
    ),
):
    """Read a persisted deliberation campaign comparison export."""
    export_payload = _load_deliberation_campaign_comparison_export(
        comparison_id,
        output_dir=output_dir,
        format=format,
    )
    _print_deliberation_campaign_comparison_export(export_payload, as_json=json_output)


@app.command("list-deliberation-campaign-comparison-exports")
def list_deliberation_campaign_comparison_exports(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum number of persisted comparison exports to list."),
    output_dir: str = typer.Option(
        str(DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR),
        "--output-dir",
        help="Directory containing persisted deliberation campaign comparison exports.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the export list as JSON."),
):
    """List persisted deliberation campaign comparison exports."""
    exports = _collect_deliberation_campaign_comparison_exports(limit=limit, output_dir=output_dir)
    _print_deliberation_campaign_comparison_export_list(
        exports,
        output_dir=output_dir,
        limit=limit,
        as_json=json_output,
    )


@app.command("replay-deliberation")
def replay_deliberation(
    deliberation_id: str,
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist the replay as a new deliberation run."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="AgentSociety backend mode: live, surrogate, or disabled."),
    json_output: bool = typer.Option(False, "--json", help="Print the replay result as JSON."),
):
    """Replay a deliberation from its persisted manifest."""
    result = replay_deliberation_sync(
        deliberation_id,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_deliberation_result(result, as_json=json_output)


@app.command("list-deliberation-targets")
def list_deliberation_targets_cmd(
    deliberation_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the interviewable targets as JSON."),
):
    """List interviewable agent/group targets for a persisted deliberation."""
    targets = list_deliberation_targets(deliberation_id)
    if json_output:
        _print_json([item.model_dump(mode="json") for item in targets])
        return
    console.print(Panel(f"[bold blue]Deliberation ID:[/bold blue] {deliberation_id}\n[bold blue]Targets:[/bold blue] {len(targets)}"))
    for item in targets:
        console.print(f"- {item.target_id} ({item.target_type.value})")


@app.command("interview-deliberation")
def interview_deliberation(
    deliberation_id: str,
    question: str = typer.Option(..., "--question", help="Question to ask about the run, a group, or an agent."),
    target_id: str | None = typer.Option(None, "--target-id", help="Agent id, group:<id>, or overview."),
    json_output: bool = typer.Option(False, "--json", help="Print the interview result as JSON."),
):
    """Interview an agent, a belief group, or the run overview after a persisted deliberation."""
    result = interview_deliberation_sync(
        deliberation_id,
        question=question,
        target_id=target_id,
    )
    _print_deliberation_interview_result(result, as_json=json_output)


@app.command("persona-chat-deliberation")
def persona_chat_deliberation(
    deliberation_id: str,
    question: str = typer.Option(..., "--question", help="Question to ask a persona target."),
    target_id: str | None = typer.Option(None, "--target-id", help="Agent or group target id. Defaults to the first agent when available."),
    output_path: str | None = typer.Option(None, "--output-path", help="Optional path to persist the persona chat session."),
    json_output: bool = typer.Option(False, "--json", help="Print the persona chat session as JSON."),
):
    """Start a bounded persona-chat session against a persisted deliberation target."""
    result = load_deliberation_result(deliberation_id)
    targets = list_deliberation_targets(deliberation_id)
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
        output_path=output_path,
    )
    html_path = (
        service.export_html(session)
        if output_path is None
        else service.export_html(session, Path(output_path).with_suffix(".html"))
    )
    if json_output:
        payload = session.model_dump(mode="json")
        payload["html_path"] = str(html_path)
        _print_json(payload)
        return
    console.print(
        Panel(
            f"[bold blue]Deliberation:[/bold blue] {deliberation_id}\n"
            f"[bold blue]Target:[/bold blue] {selected_target.target_id}\n"
            f"[bold blue]Turns:[/bold blue] {len(session.turns)}\n"
            f"[bold blue]HTML:[/bold blue] {html_path}"
        )
    )
    console.print(session.turns[-1].content)


@app.command("export-deliberation-neo4j")
def export_deliberation_neo4j(
    deliberation_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the Neo4j query bundle as JSON."),
):
    """Export a persisted deliberation graph as a Neo4j-friendly query bundle."""
    result = load_deliberation_result(deliberation_id)
    if not result.graph_path:
        raise typer.BadParameter("This deliberation has no persisted graph artifact.")
    store = GraphStore.load(result.graph_path)
    bundle = Neo4jFriendlyGraphBackendAdapter(store).export()
    if json_output:
        _print_json(bundle.model_dump(mode="json"))
        return
    console.print(Panel(f"[bold blue]Graph:[/bold blue] {result.graph_path}\n[bold blue]Queries:[/bold blue] {len(bundle.query_bundle.statements) if bundle.query_bundle else 0}"))


@app.command("bridge-deliberation-market")
def bridge_deliberation_market(
    deliberation_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the market/social bridge report as JSON."),
):
    """Project a persisted deliberation run into a bounded market/social bridge report."""
    result = load_deliberation_result(deliberation_id)
    bridge = DeepMarketSocialBridge()
    bridge_report = bridge.run(
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
    if json_output:
        _print_json(bridge_report.model_dump(mode="json"))
        return
    console.print(
        Panel(
            f"[bold blue]Bridge ID:[/bold blue] {bridge_report.bridge_id}\n"
            f"[bold blue]Best Scenario:[/bold blue] {bridge_report.best_scenario_id}\n"
            f"[bold blue]Bridge Score:[/bold blue] {bridge_report.bridge_score:.3f}"
        )
    )


@prediction_markets_app.command("advise")
def prediction_markets_advise(
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Venue slug when market id is unknown."),
    evidence: list[str] = typer.Option([], "--evidence", help="Inline evidence note. Repeat to add more."),
    decision_packet_path: str | None = typer.Option(None, "--decision-packet", help="Optional JSON file containing a social DecisionPacket-like payload."),
    deliberation_id: str | None = typer.Option(None, "--deliberation-id", help="Optional deliberation id whose persisted decision_packet should be reused."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend mode: surrogate or live."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist run artifacts."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
):
    """Run the prediction markets advisor on one market."""
    payload = advise_market_sync(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence,
        decision_packet=_resolve_prediction_markets_decision_packet(
            decision_packet_path=decision_packet_path,
            deliberation_id=deliberation_id,
        ),
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("paper")
def prediction_markets_paper(
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Venue slug when market id is unknown."),
    evidence: list[str] = typer.Option([], "--evidence", help="Inline evidence note. Repeat to add more."),
    decision_packet_path: str | None = typer.Option(None, "--decision-packet", help="Optional JSON file containing a social DecisionPacket-like payload."),
    deliberation_id: str | None = typer.Option(None, "--deliberation-id", help="Optional deliberation id whose persisted decision_packet should be reused."),
    stake: float = typer.Option(10.0, "--stake", help="Paper position size."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend mode: surrogate or live."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist paper trade artifacts."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
):
    """Propose a paper trade from the advisor output."""
    payload = paper_trade_market_sync(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence,
        decision_packet=_resolve_prediction_markets_decision_packet(
            decision_packet_path=decision_packet_path,
            deliberation_id=deliberation_id,
        ),
        stake=stake,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("risk")
def prediction_markets_risk(
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Venue slug when market id is unknown."),
    evidence: list[str] = typer.Option([], "--evidence", help="Inline evidence note. Repeat to add more."),
    decision_packet_path: str | None = typer.Option(None, "--decision-packet", help="Optional JSON file containing a social DecisionPacket-like payload."),
    deliberation_id: str | None = typer.Option(None, "--deliberation-id", help="Optional deliberation id whose persisted decision_packet should be reused."),
    stake: float = typer.Option(10.0, "--stake", help="Reference stake used to size the risk envelope."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend mode: surrogate or live."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist risk artifacts."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
):
    """Evaluate market risk and return the derived allocation envelope."""
    payload = assess_market_risk_sync(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence,
        decision_packet=_resolve_prediction_markets_decision_packet(
            decision_packet_path=decision_packet_path,
            deliberation_id=deliberation_id,
        ),
        stake=stake,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("allocate")
def prediction_markets_allocate(
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Venue slug when market id is unknown."),
    evidence: list[str] = typer.Option([], "--evidence", help="Inline evidence note. Repeat to add more."),
    decision_packet_path: str | None = typer.Option(None, "--decision-packet", help="Optional JSON file containing a social DecisionPacket-like payload."),
    deliberation_id: str | None = typer.Option(None, "--deliberation-id", help="Optional deliberation id whose persisted decision_packet should be reused."),
    stake: float = typer.Option(10.0, "--stake", help="Reference stake used to size the allocation."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend mode: surrogate or live."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist allocation artifacts."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
):
    """Run the portfolio allocator on one market using the advisor output."""
    payload = allocate_market_sync(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence,
        decision_packet=_resolve_prediction_markets_decision_packet(
            decision_packet_path=decision_packet_path,
            deliberation_id=deliberation_id,
        ),
        stake=stake,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("shadow")
def prediction_markets_shadow(
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Venue slug when market id is unknown."),
    evidence: list[str] = typer.Option([], "--evidence", help="Inline evidence note. Repeat to add more."),
    decision_packet_path: str | None = typer.Option(None, "--decision-packet", help="Optional JSON file containing a social DecisionPacket-like payload."),
    deliberation_id: str | None = typer.Option(None, "--deliberation-id", help="Optional deliberation id whose persisted decision_packet should be reused."),
    stake: float = typer.Option(10.0, "--stake", help="Reference shadow stake."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend mode: surrogate or live."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist shadow execution artifacts."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
):
    """Run a bounded shadow-execution pass using the same advisory pipeline."""
    payload = shadow_trade_market_sync(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence,
        decision_packet=_resolve_prediction_markets_decision_packet(
            decision_packet_path=decision_packet_path,
            deliberation_id=deliberation_id,
        ),
        stake=stake,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("live")
def prediction_markets_live(
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Market slug."),
    evidence: list[str] = typer.Option([], "--evidence", help="Optional evidence note."),
    decision_packet_path: str | None = typer.Option(None, "--decision-packet", help="Path to a decision packet JSON file."),
    deliberation_id: str | None = typer.Option(None, "--deliberation-id", help="Optional deliberation id whose persisted decision_packet should be reused."),
    stake: float = typer.Option(10.0, "--stake", help="Requested stake."),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Keep dry-run safety on unless explicitly disabled."),
    allow_live_execution: bool = typer.Option(False, "--allow-live-execution/--no-allow-live-execution", help="Permit bounded live mode."),
    authorized: bool = typer.Option(False, "--authorized/--not-authorized", help="Execution auth flag."),
    compliance_approved: bool = typer.Option(False, "--compliance-approved/--compliance-pending", help="Compliance approval flag."),
    require_human_approval_before_live: bool = typer.Option(False, "--require-human-approval-before-live/--no-require-human-approval-before-live", help="Require an explicit human approval token before any live projection can stay live."),
    human_approval_passed: bool = typer.Option(False, "--human-approved/--human-not-approved", help="Mark that a human approver has cleared this live request."),
    human_approval_actor: str = typer.Option("", "--human-approval-actor", help="Human approver label for audit."),
    human_approval_reason: str = typer.Option("", "--human-approval-reason", help="Short audit reason for the approval decision."),
    principal: str = typer.Option("", "--principal", help="Auth principal label."),
    scope: list[str] = typer.Option([], "--scope", help="Execution scopes."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist live-execution artifacts."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend override."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Run a bounded live-execution control path with dry-run safety by default."""
    payload = live_execute_market_sync(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence,
        decision_packet=_resolve_prediction_markets_decision_packet(
            decision_packet_path=decision_packet_path,
            deliberation_id=deliberation_id,
        ),
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
        scopes=scope,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("market-execution")
def prediction_markets_market_execution(
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Market slug."),
    evidence: list[str] = typer.Option([], "--evidence", help="Optional evidence note."),
    decision_packet_path: str | None = typer.Option(None, "--decision-packet", help="Path to a decision packet JSON file."),
    deliberation_id: str | None = typer.Option(None, "--deliberation-id", help="Optional deliberation id whose persisted decision_packet should be reused."),
    stake: float = typer.Option(10.0, "--stake", help="Requested stake."),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Keep dry-run safety on unless explicitly disabled."),
    allow_live_execution: bool = typer.Option(False, "--allow-live-execution/--no-allow-live-execution", help="Permit bounded live mode."),
    authorized: bool = typer.Option(False, "--authorized/--not-authorized", help="Execution auth flag."),
    compliance_approved: bool = typer.Option(False, "--compliance-approved/--compliance-pending", help="Compliance approval flag."),
    require_human_approval_before_live: bool = typer.Option(False, "--require-human-approval-before-live/--no-require-human-approval-before-live", help="Require an explicit human approval token before any live projection can stay live."),
    human_approval_passed: bool = typer.Option(False, "--human-approved/--human-not-approved", help="Mark that a human approver has cleared this live request."),
    human_approval_actor: str = typer.Option("", "--human-approval-actor", help="Human approver label for audit."),
    human_approval_reason: str = typer.Option("", "--human-approval-reason", help="Short audit reason for the approval decision."),
    principal: str = typer.Option("", "--principal", help="Auth principal label."),
    scope: list[str] = typer.Option([], "--scope", help="Execution scopes."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist execution artifacts."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend override."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Materialize a bounded market-execution audit path, dry-run by default."""
    payload = market_execution_sync(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence,
        decision_packet=_resolve_prediction_markets_decision_packet(
            decision_packet_path=decision_packet_path,
            deliberation_id=deliberation_id,
        ),
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
        scopes=scope,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("research")
def prediction_markets_research(
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Venue slug when market id is unknown."),
    evidence: list[str] = typer.Option([], "--evidence", help="Inline evidence note. Repeat to add more."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend mode: surrogate or live."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist research artifacts."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
):
    """Normalize evidence notes into research findings, evidence packets, and a synthesis."""
    payload = research_market_sync(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("slippage")
def prediction_markets_slippage(
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Venue slug when market id is unknown."),
    position_side: TradeSide = typer.Option(TradeSide.yes, "--position-side", help="Contract side to acquire or sell: yes or no."),
    execution_side: TradeSide = typer.Option(TradeSide.buy, "--execution-side", help="Execution side: buy or sell."),
    requested_quantity: float | None = typer.Option(None, "--requested-quantity", help="Requested contract quantity."),
    requested_notional: float | None = typer.Option(None, "--requested-notional", help="Requested notional in quote currency."),
    limit_price: float | None = typer.Option(None, "--limit-price", help="Optional limit price guard."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend mode: surrogate or live."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist slippage artifacts."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
):
    """Estimate orderbook slippage and liquidity for a market request."""
    payload = simulate_market_slippage_sync(
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
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("microstructure")
def prediction_markets_microstructure(
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Venue slug when market id is unknown."),
    position_side: TradeSide = typer.Option(TradeSide.yes, "--position-side", help="Contract side to acquire or sell: yes or no."),
    execution_side: TradeSide = typer.Option(TradeSide.buy, "--execution-side", help="Execution side: buy or sell."),
    requested_quantity: float = typer.Option(..., "--requested-quantity", help="Requested contract quantity."),
    capital_available_usd: float | None = typer.Option(None, "--capital-available-usd", help="Optional available capital."),
    capital_locked_usd: float = typer.Option(0.0, "--capital-locked-usd", help="Capital already locked."),
    queue_ahead_quantity: float = typer.Option(0.0, "--queue-ahead-quantity", help="Queue ahead quantity."),
    spread_collapse_threshold_bps: float = typer.Option(50.0, "--spread-collapse-threshold-bps", help="Spread collapse threshold in bps."),
    collapse_liquidity_multiplier: float = typer.Option(0.35, "--collapse-liquidity-multiplier", help="Accessible liquidity multiplier under collapse."),
    limit_price: float | None = typer.Option(None, "--limit-price", help="Optional limit price guard."),
    fee_bps: float = typer.Option(0.0, "--fee-bps", help="Optional fee basis points."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend mode: surrogate or live."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist microstructure artifacts."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
):
    """Simulate market microstructure, fills, and postmortem for a market request."""
    payload = simulate_microstructure_lab_sync(
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
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("comment-intel")
def prediction_markets_comment_intel(
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Venue slug when market id is unknown."),
    comment: list[str] = typer.Option([], "--comment", help="Comment text. Repeat to add more samples."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend mode: surrogate or live."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist comment-intel artifacts."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
):
    """Summarize market comments into sentiment and narrative signals."""
    payload = analyze_market_comments_sync(
        market_id=market_id,
        slug=slug,
        comments=comment,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("manipulation-guard")
def prediction_markets_manipulation_guard(
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Venue slug when market id is unknown."),
    evidence: list[str] = typer.Option([], "--evidence", help="Inline evidence note. Repeat to add more."),
    comment: list[str] = typer.Option([], "--comment", help="Comment sample. Repeat to add more."),
    poll_count: int = typer.Option(0, "--poll-count", min=0, help="Optional number of stream polls to collect before evaluating the guard."),
    stale_after_seconds: float = typer.Option(3600.0, "--stale-after-seconds", min=0.0, help="Freshness threshold when stream polling is enabled."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend mode: surrogate or live."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist manipulation-guard artifacts."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
):
    """Evaluate whether the market context is safe enough to treat as tradable rather than signal-only."""
    payload = guard_market_manipulation_sync(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence,
        comments=comment,
        poll_count=poll_count,
        stale_after_seconds=stale_after_seconds,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("graph")
def prediction_markets_graph(
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Venue slug when market id is unknown."),
    limit: int = typer.Option(12, "--limit", min=1, help="Maximum number of markets to include in the graph."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend mode: surrogate or live."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist graph artifacts."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
):
    """Build a canonical market graph around one market and nearby candidates."""
    payload = build_market_graph_sync(
        market_id=market_id,
        slug=slug,
        limit=limit,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("cross-venue")
def prediction_markets_cross_venue(
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Venue slug when market id is unknown."),
    limit: int = typer.Option(12, "--limit", min=1, help="Maximum number of markets to compare."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend mode: surrogate or live."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist cross-venue artifacts."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
):
    """Build a cross-venue intelligence report from the normalized market pool."""
    payload = cross_venue_intelligence_sync(
        market_id=market_id,
        slug=slug,
        limit=limit,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("multi-venue-paper")
def prediction_markets_multi_venue_paper(
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Market slug."),
    limit: int = typer.Option(12, "--limit", min=1, help="Number of markets to load."),
    include_additional_venues: bool = typer.Option(True, "--include-additional-venues/--no-include-additional-venues", help="Include bootstrap multi-venue catalog."),
    target_notional_usd: float | None = typer.Option(None, "--target-notional-usd", min=0.0, help="Optional notional budget for the paper multi-venue simulation."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist multi-venue paper artifacts."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend override."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Simulate multi-venue paper execution legs without touching real capital."""
    payload = multi_venue_paper_sync(
        market_id=market_id,
        slug=slug,
        limit=limit,
        include_additional_venues=include_additional_venues,
        target_notional_usd=target_notional_usd,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("spread-monitor")
def prediction_markets_spread_monitor(
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Market slug."),
    limit: int = typer.Option(12, "--limit", min=1, help="Number of markets to load."),
    include_additional_venues: bool = typer.Option(True, "--include-additional-venues/--no-include-additional-venues", help="Include bootstrap multi-venue catalog."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist spread-monitor artifacts."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend override."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Monitor cross-venue spreads and classify them by executability."""
    payload = monitor_market_spreads_sync(
        market_id=market_id,
        slug=slug,
        limit=limit,
        include_additional_venues=include_additional_venues,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("arbitrage-lab")
def prediction_markets_arbitrage_lab(
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Market slug."),
    limit: int = typer.Option(12, "--limit", min=1, help="Number of markets to load."),
    include_additional_venues: bool = typer.Option(True, "--include-additional-venues/--no-include-additional-venues", help="Include bootstrap multi-venue catalog."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist arbitrage-lab artifacts."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend override."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Assess cross-venue opportunities without touching live capital."""
    payload = assess_market_arbitrage_sync(
        market_id=market_id,
        slug=slug,
        limit=limit,
        include_additional_venues=include_additional_venues,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("stream-open")
def prediction_markets_stream_open(
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Venue slug when market id is unknown."),
    poll_count: int = typer.Option(1, "--poll-count", min=1, help="How many polls to perform immediately."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend mode: surrogate or live."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
):
    """Open a bounded market stream, poll it immediately, and return summary + health."""
    payload = open_market_stream_sync(
        market_id=market_id,
        slug=slug,
        poll_count=poll_count,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("stream-summary")
def prediction_markets_stream_summary(
    stream_id: str,
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend mode: surrogate or live."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
):
    """Summarize one persisted market stream."""
    payload = market_stream_summary_sync(stream_id, backend_mode=backend_mode)
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("stream-health")
def prediction_markets_stream_health(
    stream_id: str,
    stale_after_seconds: float = typer.Option(3600.0, "--stale-after-seconds", min=0.0, help="Freshness threshold for stream health."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend mode: surrogate or live."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
):
    """Inspect the health of one persisted market stream."""
    payload = market_stream_health_sync(
        stream_id,
        stale_after_seconds=stale_after_seconds,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("stream-collect")
def prediction_markets_stream_collect(
    market_id: list[str] = typer.Option([], "--market-id", help="Canonical market id. Repeat to collect multiple streams."),
    slug: list[str] = typer.Option([], "--slug", help="Venue slug. Repeat to collect multiple streams."),
    stream_id: list[str] = typer.Option([], "--stream-id", help="Persisted stream id. Repeat to refresh multiple streams."),
    fanout: int = typer.Option(4, "--fanout", min=1, help="Maximum concurrent stream workers."),
    retries: int = typer.Option(1, "--retries", min=0, help="Retry attempts per stream target."),
    timeout_seconds: float = typer.Option(5.0, "--timeout-seconds", min=0.001, help="Per-stream timeout."),
    cache_ttl_seconds: float = typer.Option(60.0, "--cache-ttl-seconds", min=0.0, help="Cache freshness window."),
    prefetch: bool = typer.Option(True, "--prefetch/--no-prefetch", help="Use cached stream collection entries when fresh."),
    backpressure_limit: int = typer.Option(32, "--backpressure-limit", min=1, help="Target count threshold that activates backpressure reporting."),
    priority_strategy: str = typer.Option("freshness", "--priority-strategy", help="Target priority strategy: request_order, freshness, liquidity, hybrid."),
    poll_count: int = typer.Option(1, "--poll-count", min=1, help="Poll count for refreshed streams."),
    stale_after_seconds: float = typer.Option(3600.0, "--stale-after-seconds", min=0.0, help="Freshness threshold for refreshed health checks."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend mode: surrogate or live."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Collect multiple market streams with cache, fanout, retries, and prioritization."""
    payload = stream_collect_sync(
        market_ids=market_id,
        slugs=slug,
        stream_ids=stream_id,
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
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("worldmonitor")
def prediction_markets_worldmonitor(
    source: str = typer.Argument(..., help="Path or inline payload exported by the worldmonitor sidecar."),
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Market slug."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist sidecar artifacts."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend override."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Ingest a worldmonitor sidecar payload into research/evidence packets."""
    payload = ingest_worldmonitor_sidecar_sync(
        source,
        market_id=market_id,
        slug=slug,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("twitter-watcher")
def prediction_markets_twitter_watcher(
    source: str = typer.Argument(..., help="Path or inline payload exported by the twitter_watcher sidecar."),
    market_id: str | None = typer.Option(None, "--market-id", help="Canonical market id."),
    slug: str | None = typer.Option(None, "--slug", help="Market slug."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist sidecar artifacts."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend override."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Ingest a twitter_watcher sidecar payload into research/evidence packets."""
    payload = ingest_twitter_watcher_sidecar_sync(
        source,
        market_id=market_id,
        slug=slug,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("events")
def prediction_markets_events(
    market_id: str | None = typer.Option(None, "--market-id", help="Market id to inspect."),
    slug: str | None = typer.Option(None, "--slug", help="Market slug to inspect."),
    venue: str | None = typer.Option(None, "--venue", help="Optional venue override for additional venues."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist event artifacts."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend override."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """List related event descriptors for one market."""
    payload = market_events_sync(
        market_id=market_id,
        slug=slug,
        venue=venue,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("positions")
def prediction_markets_positions(
    market_id: str | None = typer.Option(None, "--market-id", help="Market id to inspect."),
    slug: str | None = typer.Option(None, "--slug", help="Market slug to inspect."),
    venue: str | None = typer.Option(None, "--venue", help="Optional venue override for additional venues."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist position artifacts."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend override."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Inspect cached positions for one market."""
    payload = market_positions_sync(
        market_id=market_id,
        slug=slug,
        venue=venue,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("venues")
def prediction_markets_venues(
    query: str | None = typer.Option(None, "--query", help="Optional search query for bootstrap venues."),
    limit_per_venue: int = typer.Option(2, "--limit-per-venue", min=1, help="Per-venue descriptor cap."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist venue-catalog artifacts."),
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend override."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Inspect the bootstrap multi-venue catalog and capability matrix."""
    payload = additional_venues_catalog_sync(
        query=query,
        limit_per_venue=limit_per_venue,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("reconcile")
def prediction_markets_reconcile(
    run_id: str,
    backend_mode: str | None = typer.Option(None, "--backend-mode", help="Prediction markets backend mode: surrogate or live."),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Persist reconciliation artifacts back into the run."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
):
    """Reconcile persisted paper/shadow/ledger artifacts for one prediction-markets run."""
    payload = reconcile_market_run_sync(
        run_id,
        persist=persist,
        backend_mode=backend_mode,
    )
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("replay")
def prediction_markets_replay(
    run_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the replay result as JSON."),
):
    """Replay one persisted prediction markets run."""
    payload = replay_market_run_sync(run_id)
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("replay-postmortem")
def prediction_markets_replay_postmortem(
    run_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print the replay postmortem as JSON."),
):
    """Summarize one persisted prediction markets replay deterministically."""
    payload = replay_market_postmortem_sync(run_id)
    _print_prediction_markets_payload(payload, as_json=json_output)


@prediction_markets_app.command("runs")
def prediction_markets_runs(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum number of recent runs to return."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
):
    """List recent persisted prediction markets runs."""
    payload = _collect_prediction_market_runs(limit=limit)
    _print_prediction_markets_payload(payload, as_json=json_output)


@app.command()
def resume(thread_id: str = "default_mission"):
    """Resume a paused mission (after HITL approval)."""
    graph, config = get_graph_and_config()
    config = build_resume_config(thread_id)
    
    console.print(Panel(f"[bold yellow]Resuming Mission:[/bold yellow] {thread_id}"))
    
    # Passing None resumes from the current state in the checkpointer
    for event in graph.stream(None, config):
        for node_name, state_update in event.items():
            console.print(f"[bold magenta][{node_name}][/bold magenta] executed.")
            
            # Print state summary
            if "progress_ledger" in state_update:
                pl = state_update["progress_ledger"]
                if pl.get("next_speaker"):
                    console.print(f"  → Delegating to: [bold cyan]{pl['next_speaker']}[/bold cyan]")
            if "workers_output" in state_update and state_update["workers_output"]:
                last_out = state_update["workers_output"][-1]
                status = "[green]SUCCESS[/green]" if last_out.get("success") else f"[red]FAILED[/red] ({last_out.get('error')})"
                console.print(f"  → {last_out.get('worker_name')} result: {status}")
                if not last_out.get("success"):
                    console.print(f"  → Error Detail: {last_out.get('error')}")
                else:
                    console.print(f"  → Output: {last_out.get('content', '')[:100]}...")

@app.command()
def status(
    thread_id: str = "default_mission",
    json_output: bool = typer.Option(False, "--json", help="Print mission status as JSON."),
):
    """Check the status of a mission."""
    payload = collect_mission_status_payload(thread_id)

    if json_output:
        _print_json(payload)
        return

    if not payload["found"]:
        console.print(f"[bold red]No state found for thread:[/bold red] {thread_id}")
        return

    state = payload["state"] or {}
    progress = state.get("progress", {}) if isinstance(state.get("progress", {}), dict) else {}
    current_intent = state.get("current_intent", {}) if isinstance(state.get("current_intent", {}), dict) else {}
    runtime_metadata = payload.get("runtime_metadata", {})

    console.print(
        Panel(
            f"[bold blue]Thread:[/bold blue] {thread_id}\n"
            f"[bold blue]Goal:[/bold blue] {state.get('goal')}\n"
            f"[bold blue]Intent:[/bold blue] {current_intent.get('intent_id', 'n/a')}\n"
            f"[bold blue]Task Type:[/bold blue] {runtime_metadata.get('task_type', 'n/a')}\n"
            f"[bold blue]Mission Runtime:[/bold blue] {runtime_metadata.get('mission_runtime', 'langgraph')}\n"
            f"[bold blue]Orchestrator Runtime:[/bold blue] {runtime_metadata.get('orchestrator_runtime', 'n/a')}\n"
            f"[bold blue]Fallback Used:[/bold blue] {'yes' if runtime_metadata.get('orchestrator_fallback_used') else 'no'}\n"
            f"[bold blue]Engine Preference:[/bold blue] {runtime_metadata.get('engine_preference', 'n/a')}\n"
            f"[bold blue]Simulation Run:[/bold blue] {runtime_metadata.get('simulation_run_id', 'n/a')}\n"
            f"[bold blue]Simulation:[/bold blue] {runtime_metadata.get('simulation_status', 'n/a')}\n"
            f"[bold blue]Step:[/bold blue] {progress.get('step_index')}\n"
            f"[bold blue]Tokens Used:[/bold blue] {state.get('tokens_used_total', 0)}\n"
            f"[bold blue]Next Node(s):[/bold blue] {payload.get('next_nodes') or 'FINISHED'}"
        )
    )

if __name__ == "__main__":
    app()
