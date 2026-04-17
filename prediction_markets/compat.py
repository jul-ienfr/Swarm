from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import requests

from .additional_venues import (
    AdditionalVenueProfile,
    AdditionalVenueRegistry,
    VenueCapabilityMatrix,
    build_additional_venue_registry,
)
from .arbitrage_lab import ArbitrageLabReport, assess_arbitrage
from .adapters import _resolve_polymarket_execution_runtime_config
from .capital_ledger import CapitalLedger, CapitalLedgerChange, CapitalLedgerStore
from .cross_venue import CrossVenueIntelligence, CrossVenueIntelligenceReport
from .execution_projection import ExecutionProjectionRuntime, build_execution_compliance_snapshot
from .live_execution import (
    ExecutionAuthContext,
    LiveExecutionEngine,
    LiveExecutionPolicy,
    ExecutionProjection as LiveExecutionProjection,
    ExecutionProjectionMode as LiveExecutionProjectionMode,
    ExecutionProjectionVerdict as LiveExecutionProjectionVerdict,
    LiveExecutionRecord,
    LiveExecutionRequest,
    LiveExecutionStore,
)
from .market_execution import MarketExecutionEngine, MarketExecutionOrder, MarketExecutionReport, MarketExecutionStore
from .manipulation_guard import ManipulationGuard, ManipulationGuardReport
from .market_comment_intel import CommentRecord, MarketCommentIntel, MarketCommentIntelReport
from .market_graph import MarketGraph, MarketGraphBuilder
from .market_risk import MarketRiskReport, assess_market_risk
from .multi_venue_executor import MultiVenueExecutionReport, build_multi_venue_execution_report
from .multi_venue_paper import MultiVenuePaperReport, build_multi_venue_paper_report
from .microstructure_lab import MicrostructureReport, simulate_microstructure_lab
from .models import (
    AdvisorArchitectureStage,
    AdvisorArchitectureSurface,
    CapitalLedgerSnapshot,
    DecisionAction,
    DecisionPacket,
    EvidencePacket,
    ForecastPacket,
    ForecastComparisonSurface,
    ExecutionComplianceSnapshot,
    ExecutionProjection,
    ExecutionProjectionMode,
    ExecutionProjectionOutcome,
    ExecutionReadiness,
    MarketDescriptor,
    MarketRecommendationPacket,
    MarketSnapshot,
    MarketUniverseConfig,
    ReplayReport,
    VenueHealthReport,
    ResolutionPolicy,
    RunManifest,
    PacketCompatibilityMode,
    TradeSide,
    TradeIntent,
    VenueName,
    VenueType,
)
from .paper_trading import PaperTradeSimulation, PaperTradeSimulator, PaperTradeStatus, PaperTradeStore
from .paths import PredictionMarketPaths, default_prediction_market_paths
from .polymarket import build_polymarket_client
from .portfolio_allocator import AllocationDecision, AllocationRequest, PortfolioAllocator
from .reconciliation import ReconciliationEngine, ReconciliationReport, ReconciliationStore
from .registry import RunRegistry as RunRegistryIndex
from .registry import RunRegistryEntry, RunRegistryStore
from .registry import DEFAULT_VENUE_EXECUTION_REGISTRY
from .resolution_guard import ResolutionGuardReport, evaluate_resolution_policy
from .evidence_registry import EvidenceRegistry
from .research import (
    ResearchBridgeBundle,
    ResearchFinding,
    ResearchPipelineSurface,
    ResearchSynthesis,
    build_research_abstention_metrics,
    build_research_pipeline_surface,
    build_sidecar_research_bundle,
    findings_to_evidence,
    normalize_findings,
    synthesize_research,
)
from .replay import build_replay_postmortem, _report_surface_context
from .shadow_execution import ShadowExecutionEngine, ShadowExecutionResult, ShadowExecutionStore
from .slippage_liquidity import SlippageLiquidityReport, simulate_slippage_liquidity
from .spread_monitor import SpreadMonitorReport, monitor_spreads
from .storage import ensure_storage_layout, load_json, save_json, utc_isoformat
from .streaming import (
    MarketStreamHealth,
    MarketStreamSummary,
    MarketStreamer,
    StreamCollectionPriority,
    StreamCollectionReport,
    collect_market_streams,
)
from .universe import MarketUniverse
from .trade_intent_guard import TradeIntentGuardReport, evaluate_trade_intent_guard
from .twitter_watcher_sidecar import TwitterWatcherSidecarBridge, TwitterWatcherSidecarBundle
from .worldmonitor_sidecar import WorldMonitorSidecarBridge, WorldMonitorSidecarBundle


POSITIVE_TOKENS = (
    "bull",
    "improv",
    "beat",
    "up",
    "higher",
    "strong",
    "win",
    "yes",
    "positive",
)
NEGATIVE_TOKENS = (
    "bear",
    "down",
    "lower",
    "weak",
    "lose",
    "no",
    "negative",
    "risk",
    "concern",
)

DEFAULT_LEDGER_CASH = 1000.0


def _compat_env_text(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _resolve_live_transport_endpoint(path_or_url: str | None, *, base_url: str | None = None) -> str | None:
    candidate = str(path_or_url or "").strip()
    if not candidate:
        return None
    parsed_candidate = urlparse(candidate)
    if parsed_candidate.scheme in {"http", "https"} and parsed_candidate.netloc:
        return candidate

    normalized_base = str(base_url or "").strip()
    if not normalized_base:
        return None
    parsed_base = urlparse(normalized_base)
    if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
        return None
    return urljoin(normalized_base.rstrip("/") + "/", candidate.lstrip("/"))


def _build_live_transport_headers(auth_token: str | None, auth_scheme: str | None) -> dict[str, str]:
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
    }
    token = str(auth_token or "").strip()
    if not token:
        return headers

    scheme = str(auth_scheme or "bearer").strip()
    normalized_scheme = scheme.lower()
    if normalized_scheme in {"none", "disabled"}:
        return headers
    if normalized_scheme == "bearer":
        headers["authorization"] = f"Bearer {token}"
        return headers
    if normalized_scheme == "token":
        headers["authorization"] = f"Token {token}"
        return headers
    if normalized_scheme in {"raw", "header"}:
        headers["authorization"] = token
        return headers
    headers["authorization"] = f"{scheme} {token}"
    return headers


def _fallback_external_order_id(payload: dict[str, Any], *, order: MarketExecutionOrder, action: str) -> str:
    candidates = [
        payload.get("venue_order_id"),
        payload.get("order_id"),
        payload.get("id"),
        payload.get("external_order_id"),
    ]
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return text
    return f"external_{action}_{order.execution_id}_{order.order_id}"


def _normalize_live_transport_response(
    payload: Any,
    *,
    action: str,
    order: MarketExecutionOrder,
    order_path: str,
    cancel_path: str,
) -> dict[str, Any]:
    normalized = dict(payload) if isinstance(payload, dict) else {"value": payload}
    normalized.setdefault("venue_order_id", _fallback_external_order_id(normalized, order=order, action=action))
    normalized.setdefault("venue_order_source", "external")
    normalized.setdefault("venue_order_status", "submitted" if action == "place" else "cancelled")
    normalized.setdefault("venue_order_path", order_path)
    normalized.setdefault("venue_order_cancel_path", cancel_path)
    normalized.setdefault("venue_order_trace_kind", "external_live")
    normalized.setdefault(
        "venue_order_flow",
        "submitted->acknowledged" if action == "place" else "cancelled",
    )
    return normalized


def _request_live_transport(
    *,
    action: str,
    endpoint: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    order: MarketExecutionOrder,
    order_path: str,
    cancel_path: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        response = requests.post(
            endpoint,
            headers=headers,
            data=json.dumps(payload),
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"live_transport_request_failed:{type(exc).__name__}") from exc

    try:
        parsed_payload = response.json()
    except ValueError:
        parsed_payload = {
            "response_status_code": response.status_code,
            "response_text": response.text,
        }

    if not response.ok:
        raise RuntimeError(f"live_transport_http_error:{response.status_code}")

    return _normalize_live_transport_response(
        parsed_payload,
        action=action,
        order=order,
        order_path=order_path,
        cancel_path=cancel_path,
    )


def _build_default_live_execution_transport_bindings() -> tuple[
    dict[VenueName, Callable[[MarketExecutionOrder, dict[str, Any]], Any]],
    dict[VenueName, Callable[[MarketExecutionOrder, dict[str, Any]], Any]],
]:
    runtime_config = _resolve_polymarket_execution_runtime_config()
    selected_backend_mode = str(runtime_config.get("selected_backend_mode") or "auto").strip().lower()
    mock_transport = bool(runtime_config.get("mock_transport", False))
    auth_token = _compat_env_text(
        "POLYMARKET_EXECUTION_AUTH_TOKEN",
        "POLYMARKET_AUTH_TOKEN",
        "POLYMARKET_API_KEY",
        "POLYMARKET_CLOB_API_KEY",
    )
    auth_scheme = str(runtime_config.get("auth_scheme") or "bearer").strip() or "bearer"
    execution_base_url = _compat_env_text(
        "POLYMARKET_EXECUTION_BASE_URL",
        "POLYMARKET_EXECUTION_API_BASE_URL",
    )
    live_order_url = _resolve_live_transport_endpoint(
        str(runtime_config.get("live_order_path") or "").strip() or None,
        base_url=execution_base_url,
    )
    cancel_order_url = _resolve_live_transport_endpoint(
        str(runtime_config.get("cancel_order_path") or "").strip() or None,
        base_url=execution_base_url,
    )

    if (
        selected_backend_mode != "live"
        or mock_transport
        or not auth_token
        or not live_order_url
        or not cancel_order_url
    ):
        return {}, {}

    headers = _build_live_transport_headers(auth_token, auth_scheme)
    timeout_ms = _compat_env_text("POLYMARKET_EXECUTION_TIMEOUT_MS")
    timeout_seconds = max(1.0, float(timeout_ms) / 1000.0) if timeout_ms else 10.0

    def _submit_order(order: MarketExecutionOrder, request_payload: dict[str, Any]) -> dict[str, Any]:
        envelope = {
            "action": "place_order",
            "venue": VenueName.polymarket.value,
            "order": order.model_dump(mode="json"),
            "request": dict(request_payload or {}),
            "source": "prediction_markets.compat",
        }
        return _request_live_transport(
            action="place",
            endpoint=live_order_url,
            headers=headers,
            payload=envelope,
            order=order,
            order_path=live_order_url,
            cancel_path=cancel_order_url,
            timeout_seconds=timeout_seconds,
        )

    def _cancel_order(order: MarketExecutionOrder, request_payload: dict[str, Any]) -> dict[str, Any]:
        envelope = {
            "action": "cancel_order",
            "venue": VenueName.polymarket.value,
            "order": order.model_dump(mode="json"),
            "request": dict(request_payload or {}),
            "source": "prediction_markets.compat",
        }
        return _request_live_transport(
            action="cancel",
            endpoint=cancel_order_url,
            headers=headers,
            payload=envelope,
            order=order,
            order_path=live_order_url,
            cancel_path=cancel_order_url,
            timeout_seconds=timeout_seconds,
        )

    return (
        {VenueName.polymarket: _submit_order},
        {VenueName.polymarket: _cancel_order},
    )


def _coerce_root(base_dir: str | Path | None = None) -> Path:
    return ensure_storage_layout(base_dir)


def _prediction_market_paths(base_dir: str | Path | None = None) -> PredictionMarketPaths:
    root = _coerce_root(base_dir)
    paths = PredictionMarketPaths(root=root)
    paths.ensure_layout()
    return paths


def _generate_run_id(prefix: str = "pm_run") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _requested_projection_mode(surface_mode: str) -> ExecutionProjectionMode:
    if surface_mode in {"shadow", "shadow_trade"}:
        return ExecutionProjectionMode.shadow
    if surface_mode in {"live_execution", "market_execution"}:
        return ExecutionProjectionMode.live
    return ExecutionProjectionMode.paper


def _to_live_execution_projection(projection: ExecutionProjection) -> LiveExecutionProjection:
    verdict_map = {
        "ready": LiveExecutionProjectionVerdict.allowed,
        "degraded": LiveExecutionProjectionVerdict.downgraded,
        "blocked": LiveExecutionProjectionVerdict.blocked,
    }
    return LiveExecutionProjection(
        projection_id=projection.projection_id,
        run_id=projection.run_id,
        venue=projection.venue,
        market_id=projection.market_id,
        requested_mode=projection.requested_mode.value,
        projected_mode=projection.projected_mode.value,
        projection_verdict=verdict_map[projection.projection_verdict.value],
        blocking_reasons=list(projection.blocking_reasons),
        downgrade_reasons=list(projection.downgrade_reasons),
        manual_review_required=projection.manual_review_required,
        readiness_ref=projection.readiness_ref,
        compliance_ref=projection.compliance_ref,
        capital_ref=projection.capital_ref,
        reconciliation_ref=projection.reconciliation_ref,
        health_ref=projection.health_ref,
        highest_safe_mode=None if projection.highest_safe_mode is None else projection.highest_safe_mode.value,
        highest_authorized_mode=projection.highest_authorized_mode.value,
        expires_at=projection.expires_at,
        summary=projection.summary,
        metadata=dict(projection.metadata),
    )


def _shadow_postmortem_surface(shadow_execution: ShadowExecutionResult) -> dict[str, Any]:
    payload = shadow_execution.model_dump(mode="json")
    paper_trade = shadow_execution.paper_trade
    payload["paper_trade_postmortem"] = (
        None if paper_trade is None else paper_trade.postmortem().model_dump(mode="json")
    )
    return payload


def _slippage_postmortem_surface(report: SlippageLiquidityReport) -> dict[str, Any]:
    return report.postmortem().model_dump(mode="json")


def _microstructure_postmortem_surface(report: MicrostructureReport) -> dict[str, Any]:
    return report.postmortem().model_dump(mode="json")


def _replay_postmortem_surfaces(report_payload: dict[str, Any]) -> dict[str, Any]:
    surfaces: dict[str, Any] = {}

    shadow_postmortem = report_payload.get("shadow_postmortem")
    if shadow_postmortem is None and report_payload.get("shadow_execution") is not None:
        shadow_execution = report_payload["shadow_execution"]
        if not isinstance(shadow_execution, ShadowExecutionResult):
            shadow_execution = ShadowExecutionResult.model_validate(shadow_execution)
        shadow_postmortem = _shadow_postmortem_surface(shadow_execution)
    if shadow_postmortem is not None:
        surfaces["shadow_postmortem"] = shadow_postmortem

    slippage_postmortem = report_payload.get("slippage_postmortem")
    if slippage_postmortem is None and report_payload.get("slippage_report") is not None:
        slippage_report = report_payload["slippage_report"]
        if not isinstance(slippage_report, SlippageLiquidityReport):
            slippage_report = SlippageLiquidityReport.model_validate(slippage_report)
        slippage_postmortem = _slippage_postmortem_surface(slippage_report)
    if slippage_postmortem is not None:
        surfaces["slippage_postmortem"] = slippage_postmortem

    microstructure_postmortem = report_payload.get("microstructure_postmortem")
    if microstructure_postmortem is None and report_payload.get("microstructure_report") is not None:
        microstructure_report = report_payload["microstructure_report"]
        if not isinstance(microstructure_report, MicrostructureReport):
            microstructure_report = MicrostructureReport.model_validate(microstructure_report)
        microstructure_postmortem = _microstructure_postmortem_surface(microstructure_report)
    if microstructure_postmortem is not None:
        surfaces["microstructure_postmortem"] = microstructure_postmortem

    return surfaces


def _report_order_trace_audit(report_payload: dict[str, Any]) -> dict[str, Any] | None:
    surface_context = _report_surface_context(report_payload)
    order_trace_audit = surface_context.get("order_trace_audit")
    return order_trace_audit if isinstance(order_trace_audit, dict) else None


def _extract_probability(decision_packet: Any | None) -> float | None:
    payload = _surface_bridge_packet(decision_packet)
    if not isinstance(payload, dict):
        return None
    direct_keys = (
        "probability_estimate",
        "probability_yes",
        "fair_probability",
        "confidence_low",
        "confidence_high",
        "confidence",
    )
    for key in direct_keys:
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
    for nested_key in ("forecast", "decision", "metadata"):
        nested = payload.get(nested_key)
        nested_payload = _surface_bridge_packet(nested)
        if isinstance(nested_payload, dict):
            value = _extract_probability(nested_payload)
            if value is not None:
                return value
    return None


def _surface_bridge_packet(packet: Any | None) -> dict[str, Any] | None:
    if packet is None:
        return None
    if hasattr(packet, "surface") and callable(packet.surface):
        payload = packet.surface()
    elif hasattr(packet, "model_dump"):
        payload = packet.model_dump(mode="json")
    elif isinstance(packet, dict):
        payload = dict(packet)
    else:
        payload = {"value": packet}
    if isinstance(payload, dict):
        payload.setdefault("schema_version", "v1")
        payload.setdefault("packet_version", "1.0.0")
        payload.setdefault("market_only_compatible", True)
        payload.setdefault("compatibility_mode", PacketCompatibilityMode.market_only.value)
        if "packet_contract" not in payload and hasattr(packet, "contract_surface") and callable(packet.contract_surface):
            payload["packet_contract"] = packet.contract_surface()
        if "contract_id" not in payload and isinstance(payload.get("packet_contract"), dict):
            payload["contract_id"] = payload["packet_contract"].get("contract_id")
        if "packet_contract" not in payload:
            payload["packet_contract"] = {
                "contract_id": payload.get("contract_id"),
                "schema_version": payload.get("schema_version", "v1"),
                "packet_version": payload.get("packet_version", "1.0.0"),
                "packet_kind": payload.get("packet_kind", "decision"),
                "compatibility_mode": payload.get("compatibility_mode", PacketCompatibilityMode.market_only.value),
                "market_only_compatible": payload.get("market_only_compatible", True),
            }
    return payload


def _normalize_decision_packet(packet: Any | None) -> dict[str, Any] | None:
    payload = _surface_bridge_packet(packet)
    if payload is None:
        return None
    payload.setdefault("packet_kind", "decision")
    if "forecast_id" not in payload and isinstance(packet, ForecastPacket):
        payload["forecast_id"] = packet.forecast_id
    if "recommendation_id" not in payload and isinstance(packet, MarketRecommendationPacket):
        payload["recommendation_id"] = packet.recommendation_id
    return payload


def _social_bridge_metadata(packet: Any | None) -> dict[str, Any] | None:
    payload = _surface_bridge_packet(packet)
    if not isinstance(payload, dict):
        return None
    packet_contract = payload.get("packet_contract") if isinstance(payload.get("packet_contract"), dict) else {}
    return {
        "schema_version": payload.get("schema_version", "v1"),
        "packet_version": payload.get("packet_version", "1.0.0"),
        "packet_kind": payload.get("packet_kind", "decision"),
        "contract_id": payload.get("contract_id") or packet_contract.get("contract_id"),
        "packet_contract": dict(packet_contract),
        "decision_id": payload.get("decision_id"),
        "decision_action": payload.get("action"),
        "decision_confidence": payload.get("confidence"),
        "decision_probability": _extract_probability(payload),
        "source_bundle_id": payload.get("source_bundle_id"),
        "source_packet_refs": list(payload.get("source_packet_refs") or []),
        "social_context_refs": list(payload.get("social_context_refs") or []),
        "market_context_refs": list(payload.get("market_context_refs") or []),
    }


def _order_trace_audit_from_payload(
    live_record: Any | None,
    market_execution: Any | None = None,
) -> dict[str, Any] | None:
    live_metadata = dict(getattr(live_record, "metadata", {}) or {})
    market_metadata = dict(getattr(market_execution, "metadata", {}) or {}) if market_execution is not None else {}
    lifecycle = market_metadata.get("venue_order_lifecycle") or live_metadata.get("venue_order_lifecycle")
    if not isinstance(lifecycle, dict):
        return None
    live_status = getattr(getattr(live_record, "status", None), "value", str(getattr(live_record, "status", "unavailable")))
    transport_mode = "live" if lifecycle.get("venue_order_trace_kind") == "external_live" else "dry_run"
    audit = {
        "schema_version": "v1",
        "trace_source": "venue_order_lifecycle",
        "venue_order_id": lifecycle.get("venue_order_id"),
        "venue_order_status": lifecycle.get("venue_order_status"),
        "venue_order_source": lifecycle.get("venue_order_source"),
        "venue_order_status_history": list(lifecycle.get("venue_order_status_history") or []),
        "venue_order_acknowledged_at": lifecycle.get("venue_order_acknowledged_at"),
        "venue_order_acknowledged_by": lifecycle.get("venue_order_acknowledged_by"),
        "venue_order_acknowledged_reason": lifecycle.get("venue_order_acknowledged_reason"),
        "venue_order_cancel_reason": lifecycle.get("venue_order_cancel_reason"),
        "venue_order_cancelled_at": lifecycle.get("venue_order_cancelled_at"),
        "venue_order_cancelled_by": lifecycle.get("venue_order_cancelled_by"),
        "venue_order_path": lifecycle.get("venue_order_path"),
        "venue_order_cancel_path": lifecycle.get("venue_order_cancel_path"),
        "venue_order_configured": bool(lifecycle.get("venue_order_configured", False)),
        "venue_order_trace_kind": lifecycle.get("venue_order_trace_kind"),
        "venue_order_flow": lifecycle.get("venue_order_flow"),
        "live_execution_status": live_status,
        "transport_mode": transport_mode,
        "runtime_live_claimed": transport_mode == "live",
        "runtime_honest_mode": transport_mode,
        "place_auditable": True,
        "cancel_auditable": True,
    }
    if market_execution is not None:
        audit["market_execution_status"] = getattr(getattr(market_execution, "status", None), "value", str(getattr(market_execution, "status", "unavailable")))
    return audit


def _social_bridge_runbook(packet: Any | None) -> dict[str, Any]:
    payload = _social_bridge_metadata(packet)
    if payload is not None:
        return {
            "runbook_id": "social_bridge_available",
            "runbook_kind": "ok",
            "summary": "Social bridge context is available and can be used as evidence.",
            "recommended_action": "proceed",
            "owner": "system",
            "priority": "low",
            "status": "ok",
            "trigger_reasons": [],
            "next_steps": [
                "Use the bridge context in the market packet bundle.",
            ],
            "signals": {
                "social_bridge_available": True,
                "social_bridge_status": "available",
                "social_bridge_refs": list(payload.get("market_context_refs") or []),
            },
        }
    return {
        "runbook_id": "social_bridge_unavailable",
        "runbook_kind": "degraded_mode",
        "summary": "No social bridge context is available, so the run should remain market-only.",
        "recommended_action": "continue_market_only",
        "owner": "operator",
        "priority": "medium",
        "status": "degraded",
        "trigger_reasons": ["social_bridge_unavailable"],
        "next_steps": [
            "Continue the run in market-only mode.",
            "Record the missing bridge context in the run artifacts.",
            "Rebuild the bridge only when social evidence becomes available.",
        ],
        "signals": {
            "social_bridge_available": False,
            "social_bridge_status": "unavailable",
            "social_bridge_refs": [],
        },
    }


def _paper_trade_guard(report: Any) -> dict[str, Any]:
    def _value(source: Any, key: str, default: Any = None) -> Any:
        if isinstance(source, dict):
            return source.get(key, default)
        return getattr(source, key, default)

    if isinstance(report, dict):
        snapshot = report.get("snapshot")
        resolution_guard = report.get("resolution_policy") or report.get("resolution_guard")
        execution_readiness = report.get("execution_readiness")
    else:
        snapshot = getattr(report, "snapshot", None)
        resolution_guard = getattr(report, "resolution_policy", None) or getattr(report, "resolution_guard", None)
        execution_readiness = getattr(report, "execution_readiness", None)
    blocked_reasons: list[str] = []

    if snapshot is None:
        blocked_reasons.append("missing_snapshot")
    else:
        snapshot_status = _value(snapshot, "status")
        snapshot_status_value = getattr(snapshot_status, "value", snapshot_status)
        if snapshot_status_value not in {"open", "resolved"}:
            blocked_reasons.append(f"snapshot_not_tradable:{snapshot_status_value}")
        staleness_ms = _value(snapshot, "staleness_ms")
        if isinstance(staleness_ms, (int, float)) and staleness_ms > 120_000:
            blocked_reasons.append(f"snapshot_stale:{int(staleness_ms)}")

    if resolution_guard is None:
        blocked_reasons.append("missing_resolution_guard")
    else:
        if not bool(_value(resolution_guard, "approved", False)):
            blocked_reasons.append("resolution_guard_not_approved")
        if bool(_value(resolution_guard, "manual_review_required", False)):
            blocked_reasons.append("resolution_guard_manual_review_required")
        if not bool(_value(resolution_guard, "can_forecast", False)):
            blocked_reasons.append("resolution_guard_cannot_forecast")
        official_source = _value(resolution_guard, "official_source") or _value(resolution_guard, "official_source_url")
        if not official_source:
            blocked_reasons.append("resolution_guard_missing_official_source")

    if execution_readiness is not None:
        if not bool(_value(execution_readiness, "can_materialize_trade_intent", False)):
            blocked_reasons.append("execution_readiness_not_materializable")
        if bool(_value(execution_readiness, "manual_review_required", False)):
            blocked_reasons.append("execution_readiness_manual_review_required")
        blocked_reasons.extend(list(_value(execution_readiness, "blocked_reasons", []) or []))
        blocked_reasons.extend(list(_value(execution_readiness, "no_trade_reasons", []) or []))

    blocked_reasons = list(dict.fromkeys(reason for reason in blocked_reasons if reason))
    return {
        "paper_trade_allowed": not blocked_reasons,
        "paper_trade_blocked": bool(blocked_reasons),
        "paper_trade_blocked_reasons": blocked_reasons,
        "paper_trade_blocked_reason": "; ".join(blocked_reasons),
        "paper_trade_runbook": {
            "runbook_id": "paper_trade_unreliable_inputs" if blocked_reasons else "paper_trade_ready",
            "runbook_kind": "blocked" if blocked_reasons else "ok",
            "summary": (
                "Paper trading is blocked because the snapshot or resolution inputs are not reliable enough."
                if blocked_reasons
                else "Paper trading is allowed because the snapshot and resolution inputs are reliable enough."
            ),
            "recommended_action": "stay_dry_run" if blocked_reasons else "proceed",
            "owner": "operator" if blocked_reasons else "system",
            "priority": "high" if blocked_reasons else "low",
            "status": "blocked" if blocked_reasons else "ok",
            "trigger_reasons": blocked_reasons or [],
        },
    }


def _evidence_bias(evidence_inputs: list[str] | None) -> float:
    if not evidence_inputs:
        return 0.0
    bias = 0.0
    for item in evidence_inputs:
        text = item.lower()
        if any(token in text for token in POSITIVE_TOKENS):
            bias += 0.025
        if any(token in text for token in NEGATIVE_TOKENS):
            bias -= 0.025
    return max(-0.12, min(0.12, bias))


def _confidence_band(market_probability: float, signal_probability: float | None, evidence_inputs: list[str] | None) -> tuple[float, float]:
    spread = 0.12
    if signal_probability is not None:
        spread -= min(0.04, abs(signal_probability - market_probability) * 0.2)
    if evidence_inputs:
        spread -= min(0.03, 0.01 * len(evidence_inputs))
    width = max(0.05, min(0.18, spread))
    center = signal_probability if signal_probability is not None else market_probability
    return max(0.0, center - width), min(1.0, center + width)


def _confidence_band_surface(low: float, high: float, center: float | None = None) -> dict[str, float]:
    center_value = center if center is not None else (low + high) / 2.0
    return {
        "low": round(max(0.0, min(1.0, low)), 6),
        "high": round(max(0.0, min(1.0, high)), 6),
        "center": round(max(0.0, min(1.0, center_value)), 6),
        "width": round(max(0.0, high - low), 6),
    }


def _rationale_summary(rationale: str, *, fallback: str = "") -> str:
    cleaned = rationale.strip()
    if not cleaned:
        return fallback
    for separator in (". ", "; ", " - "):
        if separator in cleaned:
            return cleaned.split(separator, 1)[0].strip()
    return cleaned


def _scenario_surface(
    *,
    market_title: str,
    fair_probability: float,
    action: DecisionAction,
    fallback_action: DecisionAction | None = None,
) -> list[dict[str, Any]]:
    base_action = action.value
    fallback_value = None if fallback_action is None else fallback_action.value
    return [
        {
            "scenario": "bull",
            "summary": f"{market_title}: edge widens and the market moves toward {fair_probability:.3f}.",
            "likely_action": DecisionAction.bet.value if action == DecisionAction.bet else base_action,
        },
        {
            "scenario": "base",
            "summary": f"{market_title}: prices stay near current levels and the current guidance remains {base_action}.",
            "likely_action": fallback_value or (DecisionAction.wait.value if action == DecisionAction.wait else base_action),
        },
        {
            "scenario": "bear",
            "summary": f"{market_title}: data stays stale or resolution stays uncertain, keeping the module in {fallback_value or base_action}.",
            "likely_action": fallback_value or (DecisionAction.no_trade.value if action == DecisionAction.no_trade else base_action),
        },
    ]


def _surface_enrichment(
    *,
    descriptor: MarketDescriptor,
    snapshot: MarketSnapshot,
    forecast: ForecastPacket,
    recommendation: MarketRecommendationPacket,
    decision: DecisionPacket,
    resolution: ResolutionGuardReport,
    fallback_action: DecisionAction | None = None,
) -> dict[str, Any]:
    requires_manual_review = bool(
        forecast.manual_review_required
        or recommendation.action == DecisionAction.manual_review
        or decision.action == DecisionAction.manual_review
        or resolution.manual_review_required
    )
    return {
        "confidence_band": _confidence_band_surface(forecast.confidence_low, forecast.confidence_high, forecast.fair_probability),
        "rationale_summary": _rationale_summary(
            forecast.rationale,
            fallback=f"{descriptor.title}: {'insufficient market data' if fallback_action == DecisionAction.no_trade else 'wait for better data'}.",
        ),
        "scenarios": _scenario_surface(
            market_title=descriptor.title,
            fair_probability=forecast.fair_probability,
            action=recommendation.action,
            fallback_action=fallback_action,
        ),
        "risks": list(dict.fromkeys([*forecast.risks, *recommendation.why_not_now, *decision.why_not_now])),
        "requires_manual_review": requires_manual_review,
        "next_review_at": utc_isoformat(forecast.next_review_at),
        "resolution_policy_missing": bool(forecast.metadata.get("resolution_policy_missing", False) or not forecast.resolution_policy_ref),
        "snapshot_quality": {
            "staleness_ms": snapshot.staleness_ms,
            "spread_bps": snapshot.spread_bps,
            "liquidity": snapshot.liquidity,
            "has_orderbook": snapshot.orderbook is not None,
            "has_price_proxy": any(
                value is not None
                for value in (snapshot.market_implied_probability, snapshot.midpoint_yes, snapshot.price_yes)
            ),
        },
    }


def _build_advisor_architecture(
    *,
    run_id: str,
    descriptor: MarketDescriptor,
    snapshot: MarketSnapshot,
    resolution: ResolutionGuardReport,
    evidence_packets: list[EvidencePacket],
    forecast: ForecastPacket,
    recommendation: MarketRecommendationPacket,
    decision: DecisionPacket,
    research_bridge: ResearchBridgeBundle | None,
    execution_readiness: ExecutionReadiness | None = None,
    backend_mode: str | None = None,
) -> AdvisorArchitectureSurface:
    social_bridge_metadata = forecast.metadata.get("social_bridge")
    resolution_status = (
        "blocked" if not resolution.can_forecast else "degraded" if resolution.manual_review_required else "ready"
    )
    recommendation_status = (
        "blocked"
        if recommendation.action == DecisionAction.manual_review
        else "degraded"
        if recommendation.action in {DecisionAction.wait, DecisionAction.no_trade} or recommendation.requires_manual_review
        else "ready"
    )
    decision_status = (
        "blocked"
        if decision.action == DecisionAction.manual_review
        else "degraded"
        if decision.action in {DecisionAction.wait, DecisionAction.no_trade} or decision.requires_manual_review
        else "ready"
    )
    evidence_refs = [packet.evidence_id for packet in evidence_packets]
    readiness_status = (
        "skipped"
        if execution_readiness is None
        else "ready"
        if execution_readiness.ready_to_execute
        else "blocked"
    )
    return AdvisorArchitectureSurface(
        run_id=run_id,
        venue=descriptor.venue,
        market_id=descriptor.market_id,
        runtime="swarm",
        backend_mode=backend_mode or "auto",
        social_bridge_state="available" if social_bridge_metadata else "unavailable",
        research_bridge_state="available" if research_bridge is not None else ("ready" if evidence_refs else "unavailable"),
        packet_contracts={
            "forecast": forecast.contract_surface(),
            "recommendation": recommendation.contract_surface(),
            "decision": decision.contract_surface(),
        },
        packet_refs={
            "snapshot": snapshot.snapshot_id,
            "resolution_policy": resolution.policy_id,
            "forecast": forecast.forecast_id,
            "recommendation": recommendation.recommendation_id,
            "decision": decision.decision_id,
            "execution_readiness": None if execution_readiness is None else execution_readiness.readiness_id,
            "research_bridge": None if research_bridge is None else research_bridge.bundle_id,
        },
        stages=[
            AdvisorArchitectureStage(
                stage_id=f"{run_id}:market_context",
                stage_kind="market_context",
                role="market_data",
                status="ready",
                input_refs=[descriptor.market_id],
                output_refs=[snapshot.snapshot_id],
                summary="Resolve the canonical market descriptor and snapshot before any advisor reasoning.",
                metadata={"market_slug": descriptor.slug, "venue_type": descriptor.venue_type.value},
            ),
            AdvisorArchitectureStage(
                stage_id=f"{run_id}:resolution_guard",
                stage_kind="resolution_guard",
                role="guardrail",
                status=resolution_status,
                input_refs=[snapshot.snapshot_id, resolution.policy_id],
                output_refs=[resolution.policy_id],
                summary="Block or degrade the advisor when resolution clarity is insufficient.",
                metadata={
                    "manual_review_required": resolution.manual_review_required,
                    "can_forecast": resolution.can_forecast,
                    "reasons": list(resolution.reasons),
                },
            ),
            AdvisorArchitectureStage(
                stage_id=f"{run_id}:research_bridge",
                stage_kind="research_bridge",
                role="evidence",
                status="ready" if research_bridge is not None or evidence_refs else "skipped",
                input_refs=evidence_refs,
                output_refs=[] if research_bridge is None else [research_bridge.bundle_id],
                summary="Normalize evidence packets and optional sidecar synthesis into advisor-ready research context.",
                metadata={
                    "evidence_count": len(evidence_refs),
                    "research_bridge_present": research_bridge is not None,
                    "social_bridge_state": "available" if social_bridge_metadata else "unavailable",
                },
            ),
            AdvisorArchitectureStage(
                stage_id=f"{run_id}:forecast_packet",
                stage_kind="forecast_packet",
                role="forecast",
                status="degraded" if forecast.requires_manual_review else "ready",
                input_refs=[snapshot.snapshot_id, *evidence_refs],
                output_refs=[forecast.forecast_id],
                contract_ids=[forecast.contract_id],
                summary="Emit the canonical forecast packet that anchors recommendation and execution previews.",
                metadata={"social_bridge_used": forecast.social_bridge_used, "probability_estimate": forecast.probability_estimate},
            ),
            AdvisorArchitectureStage(
                stage_id=f"{run_id}:recommendation_packet",
                stage_kind="recommendation_packet",
                role="recommendation",
                status=recommendation_status,
                input_refs=[forecast.forecast_id],
                output_refs=[recommendation.recommendation_id],
                contract_ids=[recommendation.contract_id],
                summary="Translate the forecast into an operator-facing recommendation packet.",
                metadata={"action": recommendation.action.value, "side": None if recommendation.side is None else recommendation.side.value},
            ),
            AdvisorArchitectureStage(
                stage_id=f"{run_id}:decision_packet",
                stage_kind="decision_packet",
                role="decision",
                status=decision_status,
                input_refs=[forecast.forecast_id, recommendation.recommendation_id],
                output_refs=[decision.decision_id],
                contract_ids=[decision.contract_id],
                summary="Emit the canonical advisor decision packet for replay, audit, and downstream gating.",
                metadata={"action": decision.action.value, "confidence": decision.confidence},
            ),
            AdvisorArchitectureStage(
                stage_id=f"{run_id}:execution_readiness",
                stage_kind="execution_readiness",
                role="execution_gate",
                status=readiness_status,
                input_refs=[forecast.forecast_id, recommendation.recommendation_id, decision.decision_id],
                output_refs=[] if execution_readiness is None else [execution_readiness.readiness_id],
                summary="Project the advisor output into a safe execution-readiness verdict without forcing live execution.",
                metadata={
                    "route": None if execution_readiness is None else execution_readiness.route,
                    "risk_checks_passed": None if execution_readiness is None else execution_readiness.risk_checks_passed,
                    "blocked_reasons": [] if execution_readiness is None else list(execution_readiness.blocked_reasons),
                },
            ),
        ],
        summary=(
            f"Reference advisor architecture for {descriptor.market_id}: "
            "market context -> resolution guard -> research bridge -> forecast packet -> "
            "recommendation packet -> decision packet -> execution readiness."
        ),
        metadata={
            "market_title": descriptor.title,
            "snapshot_id": snapshot.snapshot_id,
            "resolution_policy_ref": resolution.policy_id,
        },
    )


def _resolve_snapshot(client: Any, descriptor: MarketDescriptor) -> MarketSnapshot:
    try:
        snapshot = client.get_snapshot(descriptor)
    except TypeError:
        snapshot = client.get_snapshot(descriptor.market_id)
    return snapshot


def _resolve_market(client: Any, *, market_id: str | None = None, slug: str | None = None) -> MarketDescriptor:
    if market_id:
        try:
            return client.get_market(market_id=market_id)
        except TypeError:
            return client.get_market(market_id)
    if slug:
        return client.get_market(slug=slug)
    raise ValueError("market_id or slug is required")


def _coerce_venue_name(venue: VenueName | str | None) -> VenueName | None:
    if venue in (None, ""):
        return None
    if isinstance(venue, VenueName):
        return venue
    return VenueName(str(venue))


def _resolve_market_for_venue(
    *,
    primary_client: Any,
    additional_venues: AdditionalVenueRegistry,
    market_id: str | None = None,
    slug: str | None = None,
    venue: VenueName | str | None = None,
) -> MarketDescriptor:
    venue_name = _coerce_venue_name(venue)
    if venue_name is None or venue_name == VenueName.polymarket:
        return _resolve_market(primary_client, market_id=market_id, slug=slug)
    if market_id:
        return additional_venues.get_market(venue_name, market_id)
    if slug:
        markets = additional_venues.list_markets(
            venue_name,
            config=MarketUniverseConfig(venue=venue_name, query=slug, limit=50),
            limit=50,
        )
        for market in markets:
            if market.slug == slug or market.market_id == slug:
                return market
        for market in additional_venues.list_markets(venue_name, limit=50):
            if market.slug == slug or market.market_id == slug:
                return market
        raise KeyError(f"No market found for venue={venue_name.value!r} slug={slug!r}")
    raise ValueError("market_id or slug is required")


def _venue_health_report(
    *,
    venue: VenueName,
    backend_mode: str | None,
    client: Any,
) -> VenueHealthReport:
    backend_mode = backend_mode or "auto"
    if venue == VenueName.polymarket:
        try:
            health = build_polymarket_client(backend_mode).health()
            health.details.setdefault("transport", "http")
            health.details.setdefault("source", "polymarket")
            return health
        except Exception as exc:
            return VenueHealthReport(
                venue=venue,
                backend_mode=backend_mode,
                healthy=False,
                message=str(exc),
                details={
                    "issues": ["api_error"],
                    "error_type": type(exc).__name__,
                    "source": "polymarket",
                    "fallback": "surrogate",
                },
            )

    registry = build_additional_venue_registry()
    if venue in registry.list_venues():
        health = registry.health(venue)
        health.details.setdefault("source", "additional_venues")
        return health

    capability = DEFAULT_VENUE_EXECUTION_REGISTRY.capability_for(venue)
    route_supported = bool(capability.route_supported)
    live_supported = bool(capability.live_execution_supported)
    bounded_supported = bool(capability.bounded_execution_supported)
    read_only = not (route_supported or live_supported or bounded_supported)
    issues: list[str] = []
    if not route_supported:
        issues.append("route_not_supported")
    if not (live_supported or bounded_supported):
        issues.append("execution_unavailable")
    healthy = not issues
    return VenueHealthReport(
        venue=venue,
        backend_mode=backend_mode,
        healthy=healthy,
        message="healthy" if healthy else "; ".join(issues),
        details={
            "issues": issues,
            "source": "execution_registry",
            "capabilities": capability.model_dump(mode="json"),
            "read_only": read_only,
            "route_supported": route_supported,
            "live_execution_supported": live_supported,
            "bounded_execution_supported": bounded_supported,
        },
    )


def _build_forecast(
    *,
    run_id: str,
    descriptor: MarketDescriptor,
    snapshot: MarketSnapshot,
    resolution: ResolutionGuardReport,
    evidence_inputs: list[str] | None,
    decision_packet: dict[str, Any] | None,
    use_social_core: bool = False,
) -> ForecastPacket:
    market_probability = snapshot.price_yes or snapshot.midpoint_yes or snapshot.market_implied_probability or 0.5
    decision_probability = _extract_probability(decision_packet)
    base_fair_probability = market_probability + _evidence_bias(evidence_inputs)
    fair_probability = base_fair_probability
    social_bridge_used = bool(use_social_core and decision_probability is not None)
    if social_bridge_used and decision_probability is not None:
        fair_probability = (base_fair_probability * 0.65) + (decision_probability * 0.35)
    fair_probability = max(0.0, min(1.0, fair_probability))
    confidence_low, confidence_high = _confidence_band(market_probability, fair_probability, evidence_inputs)
    edge_bps = round((fair_probability - market_probability) * 10000.0, 2)
    edge_after_fees_bps = round(edge_bps - 35.0, 2)
    social_bridge_delta_bps = round((fair_probability - base_fair_probability) * 10000.0, 2) if social_bridge_used else None
    price_proxy_missing = snapshot.market_implied_probability is None and snapshot.midpoint_yes is None and snapshot.price_yes is None and snapshot.orderbook is None
    weak_data_proxy = snapshot.market_implied_probability is None and snapshot.midpoint_yes is None and snapshot.price_yes is None
    fallback_action: DecisionAction | None = None
    if price_proxy_missing or weak_data_proxy:
        fallback_action = DecisionAction.no_trade if snapshot.liquidity is None or snapshot.orderbook is None else DecisionAction.wait
    elif snapshot.staleness_ms is not None and snapshot.staleness_ms > 120000:
        fallback_action = DecisionAction.wait

    if not resolution.can_forecast:
        action = DecisionAction.manual_review
    elif fallback_action is not None:
        action = fallback_action
    elif edge_after_fees_bps >= 35.0:
        action = DecisionAction.bet
    elif edge_after_fees_bps <= -35.0:
        action = DecisionAction.no_trade
    else:
        action = DecisionAction.wait

    rationale = (
        f"{descriptor.title}: market={market_probability:.3f}, fair={fair_probability:.3f}, "
        f"edge_after_fees_bps={edge_after_fees_bps:.2f}, resolution_status={resolution.status.value}."
    )
    risks = list(dict.fromkeys(resolution.reasons + resolution.ambiguity_flags))
    if price_proxy_missing:
        risks.append("missing_price_proxy")
    if weak_data_proxy:
        risks.append("missing_midpoint_proxy")
    if snapshot.liquidity is None:
        risks.append("missing_liquidity")
    if fallback_action is not None:
        risks.append(f"fallback_action={fallback_action.value}")
    return ForecastPacket(
        run_id=run_id,
        market_id=descriptor.market_id,
        venue=descriptor.venue,
        packet_version="1.0.0",
        packet_kind="forecast",
        compatibility_mode=PacketCompatibilityMode.market_only,
        market_only_compatible=True,
        source_bundle_id=run_id,
        source_packet_refs=list(dict.fromkeys(str(item) for item in (evidence_inputs or []))),
        social_context_refs=[str(item) for item in evidence_inputs or []],
        market_context_refs=[descriptor.market_id, descriptor.slug or descriptor.market_id, snapshot.snapshot_id],
        market_implied_probability=market_probability,
        fair_probability=fair_probability,
        confidence_low=confidence_low,
        confidence_high=confidence_high,
        edge_bps=edge_bps,
        edge_after_fees_bps=edge_after_fees_bps,
        recommendation_action=action,
        manual_review_required=resolution.manual_review_required,
        rationale=rationale,
        risks=risks,
        resolution_policy_ref=resolution.policy_id,
        resolution_policy_id=resolution.policy_id,
        social_bridge_used=social_bridge_used,
        social_bridge_probability=decision_probability if social_bridge_used else None,
        social_bridge_delta_bps=social_bridge_delta_bps,
        social_bridge_mode=str((_social_bridge_metadata(decision_packet) or {}).get("packet_kind") or "decision") if social_bridge_used else None,
        metadata={
            "decision_probability": decision_probability,
            "evidence_count": len(evidence_inputs or []),
            "social_bridge": _social_bridge_metadata(decision_packet),
            "social_bridge_used": social_bridge_used,
            "social_bridge_probability": decision_probability if social_bridge_used else None,
            "social_bridge_delta_bps": social_bridge_delta_bps,
            "social_bridge_mode": str((_social_bridge_metadata(decision_packet) or {}).get("packet_kind") or "decision") if social_bridge_used else None,
            "confidence_band": _confidence_band_surface(confidence_low, confidence_high, fair_probability),
            "requires_manual_review": not resolution.can_forecast or resolution.manual_review_required,
            "rationale_summary": _rationale_summary(
                rationale,
                fallback=f"{descriptor.title}: {'no trade' if action == DecisionAction.no_trade else 'wait'} for better data.",
            ),
            "scenarios": _scenario_surface(
                market_title=descriptor.title,
                fair_probability=fair_probability,
                action=action,
                fallback_action=fallback_action,
            ),
            "risks": list(dict.fromkeys(risks)),
            "fallback_action": None if fallback_action is None else fallback_action.value,
        },
    )


def _build_recommendation(
    *,
    run_id: str,
    descriptor: MarketDescriptor,
    snapshot: MarketSnapshot,
    forecast: ForecastPacket,
    resolution: ResolutionGuardReport,
    decision_packet: dict[str, Any] | None = None,
) -> MarketRecommendationPacket:
    action = forecast.recommendation_action
    side: TradeSide | None = None
    if action == DecisionAction.bet:
        side = TradeSide.yes if forecast.fair_probability >= forecast.market_implied_probability else TradeSide.no
    why_now = [f"Forecast={forecast.fair_probability:.3f}", f"Market={forecast.market_implied_probability:.3f}"]
    why_not_now = list(dict.fromkeys(resolution.reasons + resolution.ambiguity_flags))
    watch_conditions: list[str] = []
    if resolution.manual_review_required:
        watch_conditions.append("manual_resolution_review")
    if action == DecisionAction.wait:
        watch_conditions.append("better_edge")
    if action == DecisionAction.no_trade:
        watch_conditions.append("market_dislocation")
    return MarketRecommendationPacket(
        run_id=run_id,
        forecast_id=forecast.forecast_id,
        market_id=descriptor.market_id,
        venue=descriptor.venue,
        packet_version="1.0.0",
        packet_kind="recommendation",
        compatibility_mode=PacketCompatibilityMode.market_only,
        market_only_compatible=True,
        source_bundle_id=run_id,
        source_packet_refs=[forecast.forecast_id],
        social_context_refs=list(forecast.social_context_refs),
        market_context_refs=[descriptor.market_id, snapshot.snapshot_id],
        action=action,
        side=side,
        decision_id=None,
        price_reference=snapshot.price_yes or snapshot.midpoint_yes,
        edge_bps=forecast.edge_after_fees_bps,
        why_now=why_now,
        why_not_now=why_not_now,
        watch_conditions=watch_conditions,
        human_summary=forecast.rationale,
        confidence=max(0.0, min(1.0, 1.0 - ((forecast.confidence_high - forecast.confidence_low) / 2.0))),
        social_bridge_used=forecast.social_bridge_used,
        social_bridge_probability=forecast.social_bridge_probability,
        social_bridge_delta_bps=forecast.social_bridge_delta_bps,
        social_bridge_mode=forecast.social_bridge_mode,
        metadata={
            "resolution_status": resolution.status.value,
            "social_bridge": forecast.metadata.get("social_bridge") or _social_bridge_metadata(decision_packet),
            "social_bridge_used": forecast.social_bridge_used,
            "social_bridge_probability": forecast.social_bridge_probability,
            "social_bridge_delta_bps": forecast.social_bridge_delta_bps,
            "social_bridge_mode": forecast.social_bridge_mode,
            "confidence_band": _confidence_band_surface(forecast.confidence_low, forecast.confidence_high, forecast.fair_probability),
            "requires_manual_review": forecast.manual_review_required or resolution.manual_review_required,
            "rationale_summary": _rationale_summary(
                forecast.rationale,
                fallback=f"{descriptor.title}: wait for better data.",
            ),
                "scenarios": _scenario_surface(
                    market_title=descriptor.title,
                    fair_probability=forecast.fair_probability,
                    action=action,
                    fallback_action=action if action in {DecisionAction.wait, DecisionAction.no_trade} else None,
                ),
                "risks": list(dict.fromkeys(forecast.risks + why_not_now)),
            },
        )


def _build_decision(
    *,
    run_id: str,
    descriptor: MarketDescriptor,
    forecast: ForecastPacket,
    recommendation: MarketRecommendationPacket,
    decision_packet: dict[str, Any] | None = None,
) -> DecisionPacket:
    return DecisionPacket(
        run_id=run_id,
        market_id=descriptor.market_id,
        venue=descriptor.venue,
        packet_version="1.0.0",
        packet_kind="decision",
        compatibility_mode=PacketCompatibilityMode.market_only,
        market_only_compatible=True,
        source_bundle_id=run_id,
        source_packet_refs=[forecast.forecast_id, recommendation.recommendation_id],
        social_context_refs=list(forecast.social_context_refs),
        market_context_refs=[descriptor.market_id, forecast.snapshot_id or descriptor.market_id],
        action=recommendation.action,
        confidence=recommendation.confidence,
        summary=recommendation.human_summary,
        rationale=forecast.rationale,
        forecast_id=forecast.forecast_id,
        recommendation_id=recommendation.recommendation_id,
        why_now=list(recommendation.why_now),
        why_not_now=list(recommendation.why_not_now),
        watch_conditions=list(recommendation.watch_conditions),
        social_bridge_used=forecast.social_bridge_used,
        social_bridge_probability=forecast.social_bridge_probability,
        social_bridge_delta_bps=forecast.social_bridge_delta_bps,
        social_bridge_mode=forecast.social_bridge_mode,
        metadata={
            "forecast_id": forecast.forecast_id,
            "recommendation_id": recommendation.recommendation_id,
            "social_bridge": forecast.metadata.get("social_bridge") or _social_bridge_metadata(decision_packet),
            "social_bridge_used": forecast.social_bridge_used,
            "social_bridge_probability": forecast.social_bridge_probability,
            "social_bridge_delta_bps": forecast.social_bridge_delta_bps,
            "social_bridge_mode": forecast.social_bridge_mode,
            "confidence_band": _confidence_band_surface(forecast.confidence_low, forecast.confidence_high, forecast.fair_probability),
            "requires_manual_review": forecast.manual_review_required or recommendation.action == DecisionAction.manual_review,
            "rationale_summary": _rationale_summary(
                forecast.rationale,
                fallback=f"{descriptor.title}: wait for better data.",
            ),
                "scenarios": _scenario_surface(
                    market_title=descriptor.title,
                    fair_probability=forecast.fair_probability,
                    action=recommendation.action,
                    fallback_action=recommendation.action if recommendation.action in {DecisionAction.wait, DecisionAction.no_trade} else None,
                ),
                "risks": list(dict.fromkeys(forecast.risks + recommendation.why_not_now)),
        },
    )


def _build_trade_intent(
    *,
    run_id: str,
    descriptor: MarketDescriptor,
    forecast: ForecastPacket,
    recommendation: MarketRecommendationPacket,
    allocation: AllocationDecision,
    risk_report: MarketRiskReport,
    slippage_report: SlippageLiquidityReport | None,
) -> TradeIntent:
    no_trade_reasons = list(
        dict.fromkeys(
            [
                *list(recommendation.why_not_now),
                *list(risk_report.no_trade_reasons),
                *list(allocation.no_trade_reasons),
            ]
        )
    )
    max_slippage_bps = 150.0
    if slippage_report is not None:
        max_slippage_bps = max(max_slippage_bps, float(slippage_report.total_cost_bps))
    limit_price = recommendation.price_reference
    return TradeIntent(
        run_id=run_id,
        venue=descriptor.venue,
        market_id=descriptor.market_id,
        side=recommendation.side if recommendation.action == DecisionAction.bet else None,
        size_usd=allocation.recommended_stake if allocation.recommended_stake > 0 else 0.0,
        limit_price=limit_price,
        max_slippage_bps=max_slippage_bps,
        max_unhedged_leg_ms=0,
        time_in_force="ioc",
        forecast_ref=forecast.forecast_id,
        recommendation_ref=recommendation.recommendation_id,
        risk_checks_passed=bool(allocation.should_trade and risk_report.should_trade and recommendation.action == DecisionAction.bet),
        manual_review_required=forecast.manual_review_required,
        no_trade_reasons=no_trade_reasons,
        metadata={
            "allocation_id": allocation.allocation_id,
            "risk_id": risk_report.risk_id,
            "packet_version": forecast.packet_version,
        },
    )


def _run_artifact_path(paths: PredictionMarketPaths, run_id: str, filename: str) -> Path:
    run_dir = paths.run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / filename


def _persist_manifest(paths: PredictionMarketPaths, registry: "RunRegistry", manifest: RunManifest) -> Path:
    manifest_path = paths.run_manifest_path(manifest.run_id)
    save_json(manifest_path, manifest)
    registry.record(manifest, manifest_path=manifest_path)
    return manifest_path


def persist_market_packet_bundle(
    paths: PredictionMarketPaths | str | Path | None,
    *,
    run_id: str,
    forecast: ForecastPacket,
    recommendation: MarketRecommendationPacket,
    decision: DecisionPacket,
) -> dict[str, Path]:
    resolved_paths = paths if isinstance(paths, PredictionMarketPaths) else _prediction_market_paths(paths)
    saved_paths = {
        "forecast": save_json(resolved_paths.forecast_path(run_id), forecast),
        "recommendation": save_json(resolved_paths.recommendation_path(run_id), recommendation),
        "decision": save_json(resolved_paths.decision_path(run_id), decision),
    }
    return saved_paths


def load_market_packet_bundle(
    paths: PredictionMarketPaths | str | Path | None,
    run_id: str,
) -> dict[str, ForecastPacket | MarketRecommendationPacket | DecisionPacket]:
    resolved_paths = paths if isinstance(paths, PredictionMarketPaths) else _prediction_market_paths(paths)
    return {
        "forecast": ForecastPacket.load(resolved_paths.forecast_path(run_id)),
        "recommendation": MarketRecommendationPacket.load(resolved_paths.recommendation_path(run_id)),
        "decision": DecisionPacket.load(resolved_paths.decision_path(run_id)),
    }


def load_research_bridge_bundle(
    paths: PredictionMarketPaths | str | Path | None,
    run_id: str,
) -> ResearchBridgeBundle:
    resolved_paths = paths if isinstance(paths, PredictionMarketPaths) else _prediction_market_paths(paths)
    bridge_path = _run_artifact_path(resolved_paths, run_id, "research_bridge.json")
    return ResearchBridgeBundle.load(bridge_path)


def evidence_registry_audit_sync(
    *,
    market_id: str | None = None,
    run_id: str | None = None,
    provenance_ref: str | None = None,
    source_kind: str | None = None,
    limit: int = 20,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    registry = EvidenceRegistry(_prediction_market_paths(base_dir))
    payload: dict[str, Any] = {
        "audit": registry.audit(),
        "recent": registry.list_recent(limit=limit),
    }
    if market_id is not None:
        payload["market_evidence"] = registry.list_by_market(market_id)
    if run_id is not None:
        payload["run_evidence"] = registry.list_by_run(run_id)
    if provenance_ref is not None:
        payload["provenance_evidence"] = registry.list_by_provenance_ref(provenance_ref)
    if source_kind is not None:
        payload["source_kind_evidence"] = registry.list_by_source_kind(source_kind)
    return payload


def _load_market_pool(client: Any, descriptor: MarketDescriptor, *, limit: int = 12) -> list[MarketDescriptor]:
    pool: dict[str, MarketDescriptor] = {descriptor.market_id: descriptor}
    try:
        candidates = client.list_markets(limit=max(1, limit))
    except TypeError:
        candidates = client.list_markets()
    for candidate in candidates:
        pool.setdefault(candidate.market_id, candidate)
    return list(pool.values())[: max(1, limit)]


def _append_unique_markets(target: list[MarketDescriptor], items: list[MarketDescriptor]) -> list[MarketDescriptor]:
    seen = {market.market_id for market in target}
    for item in items:
        if item.market_id in seen:
            continue
        target.append(item)
        seen.add(item.market_id)
    return target


def _simulate_paper_trade_payload(
    *,
    run_id: str,
    descriptor: MarketDescriptor,
    snapshot: MarketSnapshot,
    recommendation: MarketRecommendationPacket,
    allocation: AllocationDecision,
    risk_report: MarketRiskReport,
    ledger_before: CapitalLedgerSnapshot,
    metadata: dict[str, Any] | None = None,
) -> tuple[PaperTradeSimulation, CapitalLedgerSnapshot, CapitalLedgerChange | None]:
    if allocation.should_trade and allocation.recommended_stake > 0 and recommendation.side in {TradeSide.yes, TradeSide.no}:
        paper_trade = PaperTradeSimulator().simulate_from_recommendation(
            snapshot,
            recommendation_action=recommendation.action,
            side=recommendation.side,
            stake=allocation.recommended_stake,
            run_id=run_id,
            limit_price=recommendation.price_reference,
            metadata={"allocation_id": allocation.allocation_id, **dict(metadata or {})},
        )
        ledger_engine = CapitalLedger.from_snapshot(ledger_before)
        ledger_change = ledger_engine.apply_paper_trade(
            paper_trade,
            mark_price=snapshot.market_implied_probability or snapshot.midpoint_yes or paper_trade.reference_price,
        )
        ledger_after = ledger_engine.current_snapshot()
        return paper_trade, ledger_after, ledger_change

    paper_trade = PaperTradeSimulation(
        run_id=run_id,
        market_id=descriptor.market_id,
        venue=descriptor.venue,
        action=DecisionAction.no_trade,
        position_side=recommendation.side or TradeSide.yes,
        execution_side=TradeSide.buy,
        stake=float(allocation.requested_stake if hasattr(allocation, "requested_stake") else 0.0),
        reference_price=recommendation.price_reference or snapshot.price_yes or snapshot.midpoint_yes,
        snapshot_id=snapshot.snapshot_id,
        status=PaperTradeStatus.skipped,
        metadata={
            "reasons": allocation.no_trade_reasons or risk_report.no_trade_reasons,
            **dict(metadata or {}),
        },
    )
    return paper_trade, ledger_before.model_copy(deep=True), None


def _build_surface_execution_runtime(
    *,
    run_id: str,
    mode: str,
    descriptor: MarketDescriptor,
    snapshot: MarketSnapshot,
    decision: DecisionPacket,
    forecast: ForecastPacket,
    recommendation: MarketRecommendationPacket,
    risk_report: MarketRiskReport,
    allocation: AllocationDecision,
    trade_intent: TradeIntent,
    ledger_before: CapitalLedgerSnapshot,
    backend_mode: str | None,
    client: Any,
) -> tuple[ExecutionReadiness, ExecutionComplianceSnapshot, ExecutionProjection, VenueHealthReport, TradeIntent, TradeIntentGuardReport]:
    requested_mode = _requested_projection_mode(mode)
    no_trade_reasons = list(
        dict.fromkeys(
            [
                *list(trade_intent.no_trade_reasons),
                *list(risk_report.no_trade_reasons),
                *list(allocation.no_trade_reasons),
            ]
        )
    )
    readiness = ExecutionReadiness(
        run_id=run_id,
        market_id=descriptor.market_id,
        venue=descriptor.venue,
        decision_id=decision.decision_id,
        forecast_id=forecast.forecast_id,
        recommendation_id=recommendation.recommendation_id,
        trade_intent_id=trade_intent.intent_id,
        decision_action=recommendation.action,
        side=trade_intent.side,
        size_usd=trade_intent.size_usd,
        limit_price=trade_intent.limit_price,
        max_slippage_bps=trade_intent.max_slippage_bps,
        confidence=recommendation.confidence,
        edge_after_fees_bps=recommendation.edge_bps or 0.0,
        risk_checks_passed=trade_intent.risk_checks_passed,
        manual_review_required=bool(forecast.manual_review_required or trade_intent.manual_review_required),
        blocked_reasons=no_trade_reasons,
        no_trade_reasons=no_trade_reasons,
        route="live_candidate" if requested_mode == ExecutionProjectionMode.live and trade_intent.risk_checks_passed else ("paper" if trade_intent.risk_checks_passed else "blocked"),
        execution_notes=[
            f"surface_mode={mode}",
            f"requested_mode={requested_mode.value}",
            f"backend_mode={backend_mode or 'surrogate'}",
        ],
        metadata={
            **dict(trade_intent.metadata),
            "requested_mode": requested_mode.value,
            "allocation_id": allocation.allocation_id,
            "risk_id": risk_report.risk_id,
            "live_gate_passed": False,
        },
    )
    venue_health = _venue_health_report(
        venue=descriptor.venue,
        backend_mode=backend_mode,
        client=client,
    )
    social_bridge_metadata = forecast.metadata.get("social_bridge")
    manipulation_guard_id = risk_report.metadata.get("manipulation_guard_id")
    manipulation_guard_severity = risk_report.metadata.get("manipulation_guard_severity")
    compliance = build_execution_compliance_snapshot(
        run_id=run_id,
        market=descriptor,
        requested_mode=requested_mode,
        readiness=readiness,
        venue_health=venue_health,
        capital_snapshot=ledger_before,
        metadata={
            "surface_mode": mode,
            "social_bridge_available": bool(social_bridge_metadata),
            "social_bridge_state": "available" if social_bridge_metadata else "unavailable",
            "manipulation_guard_id": manipulation_guard_id,
            "manipulation_guard_severity": manipulation_guard_severity,
            "manipulation_guard_signal_only": bool(risk_report.metadata.get("manipulation_guard_signal_only", False)),
            "manipulation_suspicion": bool(
                risk_report.metadata.get("manipulation_guard_signal_only", False)
                or manipulation_guard_severity in {"medium", "high", "critical"}
            ),
        },
    )
    projection = ExecutionProjectionRuntime().project(
        run_id=run_id,
        market=descriptor,
        requested_mode=requested_mode,
        readiness=readiness,
        compliance=compliance,
        capital_snapshot=ledger_before,
        venue_health=venue_health,
        metadata={
            "surface_mode": mode,
            "social_bridge_available": bool(social_bridge_metadata),
            "social_bridge_state": "available" if social_bridge_metadata else "unavailable",
            "social_bridge_runbook": _social_bridge_runbook(social_bridge_metadata),
            "manipulation_guard_id": manipulation_guard_id,
            "manipulation_guard_severity": manipulation_guard_severity,
            "manipulation_guard_signal_only": bool(risk_report.metadata.get("manipulation_guard_signal_only", False)),
            "manipulation_suspicion": bool(
                risk_report.metadata.get("manipulation_guard_signal_only", False)
                or manipulation_guard_severity in {"medium", "high", "critical"}
            ),
        },
    )
    trade_intent = trade_intent.model_copy(
        update={
            "metadata": {
                **dict(trade_intent.metadata),
                "execution_readiness_id": readiness.readiness_id,
                "execution_projection_id": projection.projection_id,
                "requested_mode": requested_mode.value,
                "projected_mode": projection.projected_mode.value,
            }
        }
    )
    resolved_edge_after_fees = forecast.edge_after_fees_bps
    if resolved_edge_after_fees is None:
        resolved_edge_after_fees = recommendation.edge_bps
    trade_intent_guard = evaluate_trade_intent_guard(
        trade_intent,
        snapshot=snapshot,
        readiness=readiness,
        projection=projection,
        venue_health=venue_health,
        edge_after_fees_bps=resolved_edge_after_fees,
        metadata={
            "surface_mode": mode,
            "backend_mode": backend_mode or "surrogate",
            "forecast_id": forecast.forecast_id,
            "recommendation_id": recommendation.recommendation_id,
        },
    )
    trade_intent = trade_intent_guard.guarded_trade_intent
    return readiness, compliance, projection, venue_health, trade_intent, trade_intent_guard


class RunRegistry:
    def __init__(self, base_dir: str | Path | PredictionMarketPaths | None = None) -> None:
        if isinstance(base_dir, PredictionMarketPaths):
            self.paths = base_dir
        else:
            self.paths = _prediction_market_paths(base_dir)
        self.paths.ensure_layout()
        self._store = RunRegistryStore(self.paths)
        self._index = RunRegistryIndex.load(self.paths.registry_path)

    @classmethod
    def load(cls, path: str | Path) -> "RunRegistry":
        resolved = Path(path)
        if resolved.name == "index.json":
            return cls(resolved.parent.parent)
        return cls(resolved)

    def save(self) -> Path:
        return self._index.save(self.paths.registry_path)

    def record(self, manifest: RunManifest, *, manifest_path: str | Path) -> RunRegistryEntry:
        entry = self._index.record(manifest, manifest_path=manifest_path)
        self.save()
        return entry

    def get(self, run_id: str) -> RunRegistryEntry | None:
        return self._index.get(run_id)

    def list_entries(self) -> list[RunRegistryEntry]:
        return self._index.list_entries()

    def recent(self, limit: int = 20) -> list[RunRegistryEntry]:
        return self._index.recent(limit=limit)

    def load_manifest(self, run_id: str) -> RunManifest:
        return self._store.get_manifest(run_id)


@dataclass
class PredictionMarketAdvisor:
    base_dir: str | Path | None = None
    client: Any | None = None
    backend_mode: str | None = None

    def __post_init__(self) -> None:
        self.root = _coerce_root(self.base_dir)
        self.paths = _prediction_market_paths(self.root)
        self.client = self.client or build_polymarket_client(self.backend_mode)
        self.registry = RunRegistry(self.paths)
        self.evidence_registry = EvidenceRegistry(self.paths)
        self.additional_venues = build_additional_venue_registry()

    def market_data_surface(self) -> dict[str, Any]:
        universe = MarketUniverse(adapter=self.client)
        surface = universe.describe_data_surface()
        health_surface = universe.describe_health_surface()
        health_surface = {**health_surface, "feed_surface": surface.get("feed_surface", surface)}
        return {
            "market_data_surface": surface,
            "market_health_surface": health_surface,
        }

    def market_health_surface(self) -> dict[str, Any]:
        universe = MarketUniverse(adapter=self.client)
        data_surface = universe.describe_data_surface()
        health_surface = universe.describe_health_surface()
        health_surface = {**health_surface, "feed_surface": data_surface.get("feed_surface", data_surface)}
        return {
            "market_health_surface": health_surface,
        }

    def _build_research_context(
        self,
        *,
        descriptor: MarketDescriptor,
        run_id: str,
        evidence_inputs: list[str] | None = None,
    ) -> tuple[list[ResearchFinding], list[EvidencePacket], ResearchSynthesis | None, ResearchPipelineSurface]:
        if not evidence_inputs:
            empty_pipeline = build_research_pipeline_surface(
                [],
                market_id=descriptor.market_id,
                venue=descriptor.venue,
                run_id=run_id,
                retrieval_policy="no_inputs",
                input_count=0,
                evidence_count=0,
                applied=False,
            )
            return [], [], None, empty_pipeline
        findings = normalize_findings(
            evidence_inputs,
            market_id=descriptor.market_id,
            run_id=run_id,
        )
        evidence_packets = findings_to_evidence(
            findings,
            market_id=descriptor.market_id,
            venue=descriptor.venue,
            run_id=run_id,
        )
        synthesis = synthesize_research(
            findings,
            market_id=descriptor.market_id,
            venue=descriptor.venue,
            run_id=run_id,
        )
        pipeline = build_research_pipeline_surface(
            findings,
            market_id=descriptor.market_id,
            venue=descriptor.venue,
            run_id=run_id,
            retrieval_policy="notes_only",
            input_count=len(evidence_inputs or []),
            evidence_count=len(evidence_packets),
            applied=False,
        )
        return findings, evidence_packets, synthesis, pipeline

    def _record_evidence_packets(
        self,
        evidence_packets: list[EvidencePacket],
        *,
        run_id: str,
        market_id: str,
        source_type: str,
        source_path: str | None = None,
        classification: str | None = None,
    ) -> None:
        for evidence in evidence_packets:
            metadata = dict(evidence.metadata)
            metadata.setdefault("run_id", run_id)
            metadata.setdefault("market_id", market_id)
            metadata.setdefault("source_type", source_type)
            if source_path is not None:
                metadata.setdefault("source_path", source_path)
            if classification is not None:
                metadata.setdefault("classification", classification)
            evidence.metadata = metadata
            self.evidence_registry.add(evidence)

    def _build_market_context(
        self,
        *,
        descriptor: MarketDescriptor,
        include_additional_venues: bool = False,
        limit: int = 12,
        per_additional_venue_limit: int = 2,
    ) -> tuple[list[MarketDescriptor], dict[str, MarketSnapshot], VenueCapabilityMatrix | None, list[AdditionalVenueProfile]]:
        markets = _load_market_pool(self.client, descriptor, limit=limit)
        snapshots = {market.market_id: _resolve_snapshot(self.client, market) for market in markets}
        if not include_additional_venues:
            return markets, snapshots, None, []

        query = descriptor.question or descriptor.title or descriptor.slug or descriptor.market_id
        profiles: list[AdditionalVenueProfile] = []
        for venue in self.additional_venues.list_venues():
            profile = self.additional_venues.get_profile(venue)
            profiles.append(profile)
            extra_markets = self.additional_venues.list_markets(
                venue,
                limit=per_additional_venue_limit,
                config=MarketUniverseConfig(
                    venue=venue,
                    query=query,
                    limit=per_additional_venue_limit,
                    active_only=True,
                ),
            )
            if not extra_markets:
                extra_markets = self.additional_venues.list_markets(venue, limit=1)
            _append_unique_markets(markets, extra_markets)
            for extra_market in extra_markets:
                snapshots.setdefault(extra_market.market_id, self.additional_venues.get_snapshot(venue, extra_market.market_id))
        return markets, snapshots, self.additional_venues.describe_matrix(), profiles

    def advise(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        evidence_inputs: list[str] | None = None,
        decision_packet: Any | None = None,
        use_social_core: bool = False,
        persist: bool = True,
        record_evidence: bool = True,
        run_id: str | None = None,
        mode: str = "advise",
    ) -> dict[str, Any]:
        descriptor = _resolve_market(self.client, market_id=market_id, slug=slug)
        snapshot = _resolve_snapshot(self.client, descriptor)
        resolution = evaluate_resolution_policy(descriptor)
        run_id = run_id or _generate_run_id()
        normalized_decision_packet = _normalize_decision_packet(decision_packet)
        research_findings, evidence_packets, research_synthesis, research_pipeline = self._build_research_context(
            descriptor=descriptor,
            run_id=run_id,
            evidence_inputs=evidence_inputs,
        )
        research_abstention_policy = research_pipeline.abstention_policy
        research_signal_applied = bool(evidence_inputs) and not research_abstention_policy.abstain
        research_abstention_metrics = build_research_abstention_metrics(
            research_pipeline,
            applied=research_signal_applied,
        )
        forecast = _build_forecast(
            run_id=run_id,
            descriptor=descriptor,
            snapshot=snapshot,
            resolution=resolution,
            evidence_inputs=None if research_abstention_policy.abstain else evidence_inputs,
            decision_packet=normalized_decision_packet,
            use_social_core=use_social_core,
        )
        if record_evidence and evidence_packets:
            self._record_evidence_packets(
                evidence_packets,
                run_id=run_id,
                market_id=descriptor.market_id,
                source_type="research_market_sync",
                classification="signal",
            )
            research_bridge = build_sidecar_research_bundle(
                research_findings,
                market_id=descriptor.market_id,
                venue=descriptor.venue,
                run_id=run_id,
                sidecar_name="research_market_sync",
                sidecar_health={"healthy": True, "source": "research_market_sync"},
                classification="signal",
                classification_reasons=["research_inputs"] if evidence_inputs else [],
                source_path=f"research:{descriptor.market_id}",
                pipeline=research_pipeline.model_copy(
                    update={
                        "abstention_policy": research_abstention_policy.model_copy(update={"applied": not research_abstention_policy.abstain}),
                    }
                ),
            )
        else:
            research_bridge = None

        forecast = forecast.model_copy(
            update={
                "evidence_refs": [packet.evidence_id for packet in evidence_packets],
                "resolution_policy_id": resolution.policy_id,
                "snapshot_id": snapshot.snapshot_id,
                "metadata": {
                    **dict(forecast.metadata),
                    "research_synthesis_id": None if research_synthesis is None else research_synthesis.synthesis_id,
                    "evidence_count": len(evidence_packets),
                    "research_pipeline": research_pipeline.model_dump(mode="json"),
                    "research_abstention_policy": research_abstention_policy.model_dump(mode="json"),
                    "research_abstention_metrics": research_abstention_metrics,
                    "research_public_metrics": dict(research_pipeline.public_metrics),
                    "research_signal_applied": research_signal_applied,
                },
            }
        )
        recommendation = _build_recommendation(
            run_id=run_id,
            descriptor=descriptor,
            snapshot=snapshot,
            forecast=forecast,
            resolution=resolution,
            decision_packet=normalized_decision_packet,
        )
        decision = _build_decision(
            run_id=run_id,
            descriptor=descriptor,
            forecast=forecast,
            recommendation=recommendation,
            decision_packet=normalized_decision_packet,
        )
        surface_enrichment = _surface_enrichment(
            descriptor=descriptor,
            snapshot=snapshot,
            forecast=forecast,
            recommendation=recommendation,
            decision=decision,
            resolution=resolution,
            fallback_action=forecast.recommendation_action if forecast.recommendation_action in {DecisionAction.wait, DecisionAction.no_trade} else None,
        )
        surface_enrichment.update(
            {
                "research_pipeline": research_pipeline.model_dump(mode="json"),
                "research_abstention_policy": research_abstention_policy.model_dump(mode="json"),
                "research_abstention_metrics": research_abstention_metrics,
                "research_public_metrics": dict(research_pipeline.public_metrics),
                "research_signal_applied": research_signal_applied,
            }
        )
        advisor_architecture = _build_advisor_architecture(
            run_id=run_id,
            descriptor=descriptor,
            snapshot=snapshot,
            resolution=resolution,
            evidence_packets=evidence_packets,
            forecast=forecast,
            recommendation=recommendation,
            decision=decision,
            research_bridge=research_bridge,
            backend_mode=self.backend_mode,
        )
        forecast = forecast.model_copy(
            update={
                "metadata": {
                    **dict(forecast.metadata),
                    "advisor_architecture_id": advisor_architecture.architecture_id,
                    **surface_enrichment,
                }
            }
        )
        recommendation = recommendation.model_copy(
            update={
                "metadata": {
                    **dict(recommendation.metadata),
                    "advisor_architecture_id": advisor_architecture.architecture_id,
                    **surface_enrichment,
                }
            }
        )
        decision = decision.model_copy(
            update={
                "metadata": {
                    **dict(decision.metadata),
                    "advisor_architecture_id": advisor_architecture.architecture_id,
                    **surface_enrichment,
                }
            }
        )
        social_bridge_state = "available" if forecast.metadata.get("social_bridge") else "unavailable"
        social_bridge_runbook = _social_bridge_runbook(forecast.metadata.get("social_bridge"))

        manifest = RunManifest(
            run_id=run_id,
            venue=descriptor.venue,
            venue_type=VenueType.execution,
            market_id=descriptor.market_id,
            mode=mode,
            inputs={
                "slug": descriptor.slug,
                "market_id": descriptor.market_id,
                "evidence_inputs": evidence_inputs or [],
                "decision_packet": normalized_decision_packet or {},
                "backend_mode": self.backend_mode or "surrogate",
                "packet_version": forecast.packet_version,
                "compatibility_mode": forecast.compatibility_mode.value,
                **surface_enrichment,
            },
        )
        manifest.metadata.setdefault("social_bridge", forecast.metadata.get("social_bridge"))
        manifest.metadata.setdefault("social_bridge_state", social_bridge_state)
        manifest.metadata.setdefault("social_bridge_runbook", social_bridge_runbook)
        manifest.metadata.setdefault("advisor_architecture", advisor_architecture.model_dump(mode="json"))
        manifest.metadata.setdefault("surface_enrichment", surface_enrichment)

        payload: dict[str, Any] = {
            "run_id": run_id,
            "descriptor": descriptor,
            "market": descriptor,
            "snapshot": snapshot,
            "resolution_policy": resolution,
            "research_pipeline": research_pipeline,
            "research_abstention_policy": research_abstention_policy,
            "research_abstention_metrics": research_abstention_metrics,
            "forecast": forecast,
            "recommendation": recommendation,
            "decision": decision,
            "advisor_architecture": advisor_architecture,
            "packet_bundle": {
                "schema_version": "v1",
                "packet_version": forecast.packet_version,
                "compatibility_mode": forecast.compatibility_mode.value,
                "forecast": forecast.surface(),
                "recommendation": recommendation.surface(),
                "decision": decision.surface(),
                "advisor_architecture": advisor_architecture.model_dump(mode="json"),
                "surface_enrichment": surface_enrichment,
            },
            "research_findings": research_findings,
            "evidence_packets": evidence_packets,
            "research_synthesis": research_synthesis,
            "research_bridge": research_bridge,
            "social_bridge": forecast.metadata.get("social_bridge"),
            "social_bridge_state": social_bridge_state,
            "social_bridge_runbook": social_bridge_runbook,
            "manifest": manifest,
            "surface_enrichment": surface_enrichment,
        }

        if persist:
            run_path = self.paths.run_dir(run_id)
            run_path.mkdir(parents=True, exist_ok=True)
            manifest_path = self.paths.run_manifest_path(run_id)
            snapshot_path = self.paths.snapshot_path(run_id)
            forecast_path = self.paths.forecast_path(run_id)
            recommendation_path = self.paths.recommendation_path(run_id)
            decision_path = self.paths.decision_path(run_id)
            packet_bundle_path = _run_artifact_path(self.paths, run_id, "packet_bundle.json")
            report_path = self.paths.report_path(run_id)
            descriptor_path = self.paths.market_catalog_path(descriptor.market_id)

            manifest.snapshot_ref = str(snapshot_path)
            manifest.forecast_ref = str(forecast_path)
            manifest.recommendation_ref = str(recommendation_path)
            manifest.decision_ref = str(decision_path)
            manifest.resolution_policy_ref = resolution.policy_id
            manifest.evidence_refs = [packet.evidence_id for packet in evidence_packets]
            manifest.metadata.setdefault("packet_version", forecast.packet_version)
            manifest.metadata.setdefault("forecast_packet_kind", forecast.packet_kind)
            manifest.metadata.setdefault("recommendation_packet_kind", recommendation.packet_kind)
            manifest.metadata.setdefault("decision_packet_kind", decision.packet_kind)
            manifest.metadata.setdefault("advisor_architecture_id", advisor_architecture.architecture_id)
            manifest.metadata.setdefault("social_bridge", forecast.metadata.get("social_bridge"))
            manifest.artifact_paths = {
                "descriptor": str(descriptor_path),
                "snapshot": str(snapshot_path),
                "forecast": str(forecast_path),
                "recommendation": str(recommendation_path),
                "decision": str(decision_path),
                "packet_bundle": str(packet_bundle_path),
                "report": str(report_path),
            }
            manifest.artifact_refs = list(manifest.artifact_paths.values())

            save_json(descriptor_path, descriptor)
            save_json(snapshot_path, snapshot)
            persist_market_packet_bundle(
                self.paths,
                run_id=run_id,
                forecast=forecast,
                recommendation=recommendation,
                decision=decision,
            )
            save_json(packet_bundle_path, payload["packet_bundle"])
            save_json(report_path, payload)
            save_json(manifest_path, manifest)
            self.registry.record(manifest, manifest_path=manifest_path)
            payload["manifest"] = manifest
            self._persist_extended_artifacts(payload)

        return payload

    def market_events(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        venue: VenueName | str | None = None,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        descriptor = _resolve_market_for_venue(
            primary_client=self.client,
            additional_venues=self.additional_venues,
            market_id=market_id,
            slug=slug,
            venue=venue,
        )
        if descriptor.venue == VenueName.polymarket:
            events = self.client.get_events(descriptor.market_id)
        else:
            events = self.additional_venues.get_events(descriptor.venue, descriptor.market_id)
        run_id = run_id or _generate_run_id("pm_events")
        manifest = RunManifest(
            run_id=run_id,
            venue=descriptor.venue,
            venue_type=descriptor.venue_type,
            market_id=descriptor.market_id,
            mode="events",
            inputs={"slug": descriptor.slug, "market_id": descriptor.market_id, "venue": descriptor.venue.value},
        )
        payload = {
            "run_id": run_id,
            "descriptor": descriptor,
            "market": descriptor,
            "market_events": events,
            "manifest": manifest,
        }
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def market_positions(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        venue: VenueName | str | None = None,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        descriptor = _resolve_market_for_venue(
            primary_client=self.client,
            additional_venues=self.additional_venues,
            market_id=market_id,
            slug=slug,
            venue=venue,
        )
        if descriptor.venue == VenueName.polymarket:
            positions = self.client.get_positions(descriptor.market_id)
        else:
            positions = self.additional_venues.get_positions(descriptor.venue, descriptor.market_id)
        run_id = run_id or _generate_run_id("pm_positions")
        manifest = RunManifest(
            run_id=run_id,
            venue=descriptor.venue,
            venue_type=descriptor.venue_type,
            market_id=descriptor.market_id,
            mode="positions",
            inputs={"slug": descriptor.slug, "market_id": descriptor.market_id, "venue": descriptor.venue.value},
        )
        payload = {
            "run_id": run_id,
            "descriptor": descriptor,
            "market": descriptor,
            "market_positions": positions,
            "manifest": manifest,
        }
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def _trade_context(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        evidence_inputs: list[str] | None = None,
        decision_packet: Any | None = None,
        persist: bool = True,
        run_id: str | None = None,
        stake: float = 10.0,
        mode: str = "paper",
    ) -> dict[str, Any]:
        payload = self.advise(
            market_id=market_id,
            slug=slug,
            evidence_inputs=evidence_inputs,
            decision_packet=decision_packet,
            persist=persist,
            run_id=run_id,
            mode=mode,
        )
        descriptor: MarketDescriptor = payload["descriptor"]
        snapshot: MarketSnapshot = payload["snapshot"]
        resolution: ResolutionGuardReport = payload["resolution_policy"]
        forecast: ForecastPacket = payload["forecast"]
        recommendation: MarketRecommendationPacket = payload["recommendation"]
        starting_cash = max(DEFAULT_LEDGER_CASH, float(stake) * 20.0)
        ledger_before = CapitalLedger.from_cash(
            cash=starting_cash,
            venue=descriptor.venue,
            metadata={"source": f"{mode}_default", "run_id": payload["run_id"]},
        ).current_snapshot()
        risk_report = assess_market_risk(
            descriptor,
            snapshot,
            recommendation=recommendation,
            forecast=forecast,
            ledger=ledger_before,
            market_lookup={descriptor.market_id: descriptor},
            run_id=payload["run_id"],
        )
        resolution_policy = ResolutionPolicy(
            market_id=descriptor.market_id,
            venue=descriptor.venue,
            official_source=resolution.official_source or descriptor.resolution_source or "",
            source_url=descriptor.source_url,
            resolution_rules=list(resolution.reasons),
            ambiguity_flags=list(resolution.ambiguity_flags),
            manual_review_required=resolution.manual_review_required,
            status=resolution.status,
            metadata=dict(resolution.metadata),
        )
        manipulation_guard = ManipulationGuard().evaluate(
            descriptor,
            snapshot,
            evidence=list(payload.get("evidence_packets") or []),
            resolution_policy=resolution_policy,
        )
        if manipulation_guard.signal_only:
            no_trade_reasons = list(dict.fromkeys(
                [*risk_report.no_trade_reasons, *[f"manipulation_guard:{flag}" for flag in manipulation_guard.risk_flags]]
                or [f"manipulation_guard:{manipulation_guard.severity.value}"]
            ))
            signals = list(dict.fromkeys([*risk_report.signals, f"guard_severity={manipulation_guard.severity.value}"]))
            risk_metadata = dict(risk_report.metadata)
            risk_metadata["manipulation_guard_id"] = manipulation_guard.guard_id
            risk_metadata["manipulation_guard_severity"] = manipulation_guard.severity.value
            risk_report = risk_report.model_copy(
                update={
                    "should_trade": False,
                    "approved": False,
                    "no_trade_reasons": no_trade_reasons,
                    "signals": signals,
                    "metadata": risk_metadata,
                }
            )
        social_bridge_metadata = forecast.metadata.get("social_bridge")
        social_bridge_state = "available" if social_bridge_metadata else "unavailable"
        allocation = PortfolioAllocator().allocate(
            AllocationRequest(
                run_id=payload["run_id"],
                market=descriptor,
                snapshot=snapshot,
                forecast=forecast,
                recommendation=recommendation,
                risk_report=risk_report,
            ),
            ledger=ledger_before,
            market_lookup={descriptor.market_id: descriptor},
        )
        payload["risk_report"] = risk_report
        payload["manipulation_guard"] = manipulation_guard
        payload["social_bridge_state"] = social_bridge_state
        payload["social_bridge_runbook"] = _social_bridge_runbook(social_bridge_metadata)
        payload["allocation"] = allocation
        payload["capital_ledger_before"] = ledger_before
        if allocation.recommended_stake > 0 and recommendation.side in {TradeSide.yes, TradeSide.no}:
            payload["slippage_report"] = simulate_slippage_liquidity(
                snapshot,
                position_side=recommendation.side,
                execution_side=TradeSide.buy,
                requested_notional=allocation.recommended_stake,
                limit_price=recommendation.price_reference,
                run_id=payload["run_id"],
                market_id=descriptor.market_id,
                venue=descriptor.venue,
                fee_bps=PaperTradeSimulator().fee_bps,
                metadata={"source": mode, "allocation_id": allocation.allocation_id},
            )
        payload["trade_intent"] = _build_trade_intent(
            run_id=payload["run_id"],
            descriptor=descriptor,
            forecast=forecast,
            recommendation=recommendation,
            allocation=allocation,
            risk_report=risk_report,
            slippage_report=payload.get("slippage_report"),
        )
        (
            payload["execution_readiness"],
            payload["execution_compliance"],
            payload["execution_projection"],
            payload["venue_health"],
            payload["trade_intent"],
            payload["trade_intent_guard"],
        ) = _build_surface_execution_runtime(
            run_id=payload["run_id"],
            mode=mode,
            descriptor=descriptor,
            snapshot=payload["snapshot"],
            decision=payload["decision"],
            forecast=forecast,
            recommendation=recommendation,
            risk_report=risk_report,
            allocation=allocation,
            trade_intent=payload["trade_intent"],
            ledger_before=ledger_before,
            backend_mode=self.backend_mode,
            client=self.client,
        )
        advisor_architecture = _build_advisor_architecture(
            run_id=payload["run_id"],
            descriptor=descriptor,
            snapshot=payload["snapshot"],
            resolution=payload["resolution_policy"],
            evidence_packets=list(payload.get("evidence_packets") or []),
            forecast=forecast,
            recommendation=recommendation,
            decision=payload["decision"],
            research_bridge=payload.get("research_bridge"),
            execution_readiness=payload["execution_readiness"],
            backend_mode=self.backend_mode,
        )
        payload["advisor_architecture"] = advisor_architecture
        packet_bundle = payload.get("packet_bundle")
        if isinstance(packet_bundle, dict):
            packet_bundle["advisor_architecture"] = advisor_architecture.model_dump(mode="json")
        manifest = payload.get("manifest")
        if isinstance(manifest, RunManifest):
            manifest.metadata["advisor_architecture"] = advisor_architecture.model_dump(mode="json")
            manifest.metadata["advisor_architecture_id"] = advisor_architecture.architecture_id
        payload["metadata"] = {
            "starting_cash": starting_cash,
            "backend_mode": self.backend_mode or "surrogate",
            "social_bridge_available": bool(social_bridge_metadata),
            "social_bridge_state": social_bridge_state,
            "social_bridge_runbook": _social_bridge_runbook(social_bridge_metadata),
            "manipulation_guard_id": manipulation_guard.guard_id,
            "manipulation_guard_severity": manipulation_guard.severity.value,
            "manipulation_guard_signal_only": manipulation_guard.signal_only,
            "manipulation_suspicion": manipulation_guard.signal_only or manipulation_guard.severity.value in {"medium", "high", "critical"},
        }
        return payload

    def _persist_extended_artifacts(self, payload: dict[str, Any]) -> None:
        manifest = payload.get("manifest")
        if not isinstance(manifest, RunManifest):
            return

        run_id = payload["run_id"]
        artifact_map = {
            "descriptor": "descriptor.json",
            "snapshot": "snapshot.json",
            "resolution_policy": "resolution_policy.json",
            "market_events": "market_events.json",
            "market_positions": "market_positions.json",
            "research_findings": "research_findings.json",
            "evidence_packets": "evidence_packets.json",
            "research_synthesis": "research_synthesis.json",
            "slippage_report": "slippage_report.json",
            "manipulation_guard": "manipulation_guard.json",
            "reconciliation": "reconciliation.json",
            "risk_report": "risk_report.json",
            "allocation": "allocation.json",
            "trade_intent": "trade_intent.json",
            "trade_intent_guard": "trade_intent_guard.json",
            "execution_readiness": "execution_readiness.json",
            "execution_compliance": "execution_compliance.json",
            "execution_projection": "execution_projection.json",
            "paper_trade": "paper_trade.json",
            "paper_trade_guard": "paper_trade_guard.json",
            "shadow_postmortem": "shadow_postmortem.json",
            "slippage_postmortem": "slippage_postmortem.json",
            "microstructure_report": "microstructure_report.json",
            "microstructure_postmortem": "microstructure_postmortem.json",
            "capital_ledger_before": "capital_ledger_before.json",
            "capital_ledger_after": "capital_ledger_after.json",
            "capital_ledger_change": "capital_ledger_change.json",
            "shadow_execution": "shadow_execution.json",
            "comment_intel": "comment_intel.json",
            "market_graph": "market_graph.json",
            "cross_venue": "cross_venue.json",
            "multi_venue_execution": "multi_venue_execution.json",
            "multi_venue_paper": "multi_venue_paper.json",
            "stream_summary": "stream_summary.json",
            "stream_health": "stream_health.json",
            "live_execution": "live_execution.json",
            "market_execution": "market_execution.json",
            "spread_monitor": "spread_monitor.json",
            "arbitrage_lab": "arbitrage_lab.json",
            "research_bridge": "research_bridge.json",
            "advisor_architecture": "advisor_architecture.json",
            "social_bridge_state": "social_bridge_state.json",
            "social_bridge_runbook": "social_bridge_runbook.json",
            "worldmonitor_sidecar": "worldmonitor_sidecar.json",
            "twitter_watcher_sidecar": "twitter_watcher_sidecar.json",
            "additional_venues_matrix": "additional_venues_matrix.json",
            "market_pool": "market_pool.json",
            "additional_venue_profiles": "additional_venue_profiles.json",
        }
        for key, filename in artifact_map.items():
            value = payload.get(key)
            if value is None:
                continue
            path = _run_artifact_path(self.paths, run_id, filename)
            save_json(path, value)
            manifest.artifact_paths[key] = str(path)

        paper_trade = payload.get("paper_trade")
        if isinstance(paper_trade, PaperTradeSimulation):
            paper_path = PaperTradeStore(self.paths).save(paper_trade)
            manifest.artifact_paths.setdefault("paper_trade_store", str(paper_path))

        shadow_execution = payload.get("shadow_execution")
        if isinstance(shadow_execution, ShadowExecutionResult):
            shadow_path = ShadowExecutionStore(self.paths).save(shadow_execution)
            manifest.artifact_paths.setdefault("shadow_execution_store", str(shadow_path))

        live_execution = payload.get("live_execution")
        if isinstance(live_execution, LiveExecutionRecord):
            stored_path = LiveExecutionStore(self.paths).save(live_execution)
            manifest.artifact_paths.setdefault("live_execution_store", str(stored_path))

        market_execution = payload.get("market_execution")
        if isinstance(market_execution, MarketExecutionReport):
            stored_path = MarketExecutionStore(self.paths).save(market_execution)
            manifest.artifact_paths.setdefault("market_execution_store", str(stored_path))

        ledger_store = CapitalLedgerStore(self.paths)
        for key in ("capital_ledger_before", "capital_ledger_after"):
            ledger_snapshot = payload.get(key)
            if isinstance(ledger_snapshot, CapitalLedgerSnapshot):
                stored_path = ledger_store.save_snapshot(ledger_snapshot)
                manifest.artifact_paths.setdefault(f"{key}_store", str(stored_path))

        reconciliation = payload.get("reconciliation")
        if isinstance(reconciliation, ReconciliationReport):
            stored_path = ReconciliationStore(self.paths).save(reconciliation)
            manifest.artifact_paths.setdefault("reconciliation_store", str(stored_path))

        execution_readiness = payload.get("execution_readiness")
        if isinstance(execution_readiness, ExecutionReadiness):
            manifest.execution_readiness_ref = execution_readiness.readiness_id
        execution_compliance = payload.get("execution_compliance")
        if isinstance(execution_compliance, ExecutionComplianceSnapshot):
            manifest.execution_compliance_ref = execution_compliance.compliance_id
        execution_projection = payload.get("execution_projection")
        if isinstance(execution_projection, ExecutionProjection):
            manifest.execution_projection_ref = execution_projection.projection_id
            manifest.reconciliation_ref = execution_projection.reconciliation_ref
            manifest.health_ref = execution_projection.health_ref
        capital_before = payload.get("capital_ledger_before")
        if isinstance(capital_before, CapitalLedgerSnapshot):
            manifest.capital_ref = capital_before.snapshot_id

        manifest.artifact_refs = list(dict.fromkeys(manifest.artifact_paths.values()))
        save_json(self.paths.report_path(run_id), payload)
        _persist_manifest(self.paths, self.registry, manifest)
        payload["manifest"] = manifest

    def risk(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        evidence_inputs: list[str] | None = None,
        decision_packet: Any | None = None,
        stake: float = 10.0,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        payload = self._trade_context(
            market_id=market_id,
            slug=slug,
            evidence_inputs=evidence_inputs,
            decision_packet=decision_packet,
            persist=persist,
            run_id=run_id,
            stake=stake,
            mode="risk",
        )
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def research(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        evidence_inputs: list[str] | None = None,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        descriptor = _resolve_market(self.client, market_id=market_id, slug=slug)
        run_id = run_id or _generate_run_id("pm_research")
        research_findings, evidence_packets, research_synthesis, research_pipeline = self._build_research_context(
            descriptor=descriptor,
            run_id=run_id,
            evidence_inputs=evidence_inputs,
        )
        research_abstention_policy = research_pipeline.abstention_policy
        research_abstention_metrics = build_research_abstention_metrics(research_pipeline, applied=False)
        research_bridge = None
        if evidence_packets:
            self._record_evidence_packets(
                evidence_packets,
                run_id=run_id,
                market_id=descriptor.market_id,
                source_type="research_market_sync",
                classification="signal",
            )
            research_bridge = build_sidecar_research_bundle(
                research_findings,
                market_id=descriptor.market_id,
                venue=descriptor.venue,
                run_id=run_id,
                sidecar_name="research_market_sync",
                sidecar_health={"healthy": True, "source": "research_market_sync"},
                classification="signal",
                classification_reasons=["research_inputs"] if evidence_inputs else [],
                source_path=f"research:{descriptor.market_id}",
                pipeline=research_pipeline,
            )
        manifest = RunManifest(
            run_id=run_id,
            venue=descriptor.venue,
            venue_type=descriptor.venue_type,
            market_id=descriptor.market_id,
            mode="research",
            inputs={
                "slug": descriptor.slug,
                "market_id": descriptor.market_id,
                "evidence_count": len(evidence_inputs or []),
                "research_pipeline_summary": research_pipeline.pipeline_summary,
            },
        )
        manifest.evidence_refs = [packet.evidence_id for packet in evidence_packets]
        manifest.metadata.setdefault("research_pipeline", research_pipeline.model_dump(mode="json"))
        manifest.metadata.setdefault("research_abstention_policy", research_abstention_policy.model_dump(mode="json"))
        manifest.metadata.setdefault("research_abstention_metrics", research_abstention_metrics)
        payload = {
            "run_id": run_id,
            "descriptor": descriptor,
            "market": descriptor,
            "research_findings": research_findings,
            "evidence_packets": evidence_packets,
            "research_synthesis": research_synthesis,
            "research_pipeline": research_pipeline,
            "research_abstention_policy": research_abstention_policy,
            "research_abstention_metrics": research_abstention_metrics,
            "research_bridge": research_bridge,
            "manifest": manifest,
        }
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def slippage(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        position_side: TradeSide = TradeSide.yes,
        execution_side: TradeSide = TradeSide.buy,
        requested_quantity: float | None = None,
        requested_notional: float | None = None,
        limit_price: float | None = None,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        descriptor = _resolve_market(self.client, market_id=market_id, slug=slug)
        snapshot = _resolve_snapshot(self.client, descriptor)
        run_id = run_id or _generate_run_id("pm_slippage")
        report = simulate_slippage_liquidity(
            snapshot,
            position_side=position_side,
            execution_side=execution_side,
            requested_quantity=requested_quantity,
            requested_notional=requested_notional,
            limit_price=limit_price,
            run_id=run_id,
            market_id=descriptor.market_id,
            venue=descriptor.venue,
            fee_bps=PaperTradeSimulator().fee_bps,
            metadata={"source": "slippage_command"},
        )
        manifest = RunManifest(
            run_id=run_id,
            venue=descriptor.venue,
            venue_type=descriptor.venue_type,
            market_id=descriptor.market_id,
            mode="slippage",
            inputs={
                "slug": descriptor.slug,
                "market_id": descriptor.market_id,
                "position_side": position_side.value,
                "execution_side": execution_side.value,
                "requested_quantity": requested_quantity,
                "requested_notional": requested_notional,
                "limit_price": limit_price,
            },
        )
        payload = {
            "run_id": run_id,
            "descriptor": descriptor,
            "market": descriptor,
            "snapshot": snapshot,
            "slippage_report": report,
            "slippage_postmortem": report.postmortem(),
            "manifest": manifest,
        }
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def microstructure(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        position_side: TradeSide = TradeSide.yes,
        execution_side: TradeSide = TradeSide.buy,
        requested_quantity: float,
        capital_available_usd: float | None = None,
        capital_locked_usd: float = 0.0,
        queue_ahead_quantity: float = 0.0,
        spread_collapse_threshold_bps: float = 50.0,
        collapse_liquidity_multiplier: float = 0.35,
        limit_price: float | None = None,
        fee_bps: float = 0.0,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        descriptor = _resolve_market(self.client, market_id=market_id, slug=slug)
        snapshot = _resolve_snapshot(self.client, descriptor)
        run_id = run_id or _generate_run_id("pm_microstructure")
        report = simulate_microstructure_lab(
            snapshot,
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
            metadata={
                "source": "microstructure",
                "run_id": run_id,
                "market_id": descriptor.market_id,
                "venue": descriptor.venue.value,
            },
        )
        manifest = RunManifest(
            run_id=run_id,
            venue=descriptor.venue,
            venue_type=descriptor.venue_type,
            market_id=descriptor.market_id,
            mode="microstructure",
            inputs={
                "slug": descriptor.slug,
                "market_id": descriptor.market_id,
                "position_side": position_side.value,
                "execution_side": execution_side.value,
                "requested_quantity": requested_quantity,
                "capital_available_usd": capital_available_usd,
                "capital_locked_usd": capital_locked_usd,
                "queue_ahead_quantity": queue_ahead_quantity,
                "spread_collapse_threshold_bps": spread_collapse_threshold_bps,
                "collapse_liquidity_multiplier": collapse_liquidity_multiplier,
                "limit_price": limit_price,
                "fee_bps": fee_bps,
            },
        )
        payload = {
            "run_id": run_id,
            "descriptor": descriptor,
            "market": descriptor,
            "snapshot": snapshot,
            "microstructure_report": report,
            "microstructure_postmortem": report.postmortem(),
            "manifest": manifest,
        }
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def manipulation_guard(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        evidence_inputs: list[str] | None = None,
        comments: list[str] | None = None,
        poll_count: int = 0,
        stale_after_seconds: float = 3600.0,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        descriptor = _resolve_market(self.client, market_id=market_id, slug=slug)
        snapshot = _resolve_snapshot(self.client, descriptor)
        resolution = evaluate_resolution_policy(descriptor)
        run_id = run_id or _generate_run_id("pm_guard")
        research_findings, evidence_packets, research_synthesis, research_pipeline = self._build_research_context(
            descriptor=descriptor,
            run_id=run_id,
            evidence_inputs=evidence_inputs,
        )
        research_abstention_metrics = build_research_abstention_metrics(research_pipeline, applied=False)
        comment_report = None
        if comments:
            comment_report = MarketCommentIntel().analyze(
                [CommentRecord(text=item) for item in comments],
                market_id=descriptor.market_id,
                venue=descriptor.venue,
                market_title=descriptor.title,
                market_question=descriptor.question,
            )
        stream_summary = None
        stream_health = None
        if poll_count > 0:
            streamer = MarketStreamer(client=self.client, backend_mode=self.backend_mode, paths=self.paths)
            session = streamer.open(market_id=descriptor.market_id)
            session.poll_many(count=max(1, poll_count))
            stream_summary = session.summarize()
            stream_health = session.health(stale_after_seconds=stale_after_seconds)
        resolution_policy = ResolutionPolicy(
            market_id=descriptor.market_id,
            venue=descriptor.venue,
            official_source=resolution.official_source or descriptor.resolution_source or "",
            source_url=descriptor.source_url,
            resolution_rules=list(resolution.reasons),
            ambiguity_flags=list(resolution.ambiguity_flags),
            manual_review_required=resolution.manual_review_required,
            status=resolution.status,
            metadata=dict(resolution.metadata),
        )
        report = ManipulationGuard().evaluate(
            descriptor,
            snapshot,
            comment_report=comment_report,
            stream_summary=stream_summary,
            stream_health=stream_health,
            evidence=evidence_packets,
            resolution_policy=resolution_policy,
        )
        manifest = RunManifest(
            run_id=run_id,
            venue=descriptor.venue,
            venue_type=descriptor.venue_type,
            market_id=descriptor.market_id,
            mode="manipulation_guard",
            inputs={
                "slug": descriptor.slug,
                "market_id": descriptor.market_id,
                "evidence_count": len(evidence_inputs or []),
                "comment_count": len(comments or []),
                "poll_count": poll_count,
            },
        )
        manifest.evidence_refs = [packet.evidence_id for packet in evidence_packets]
        manifest.metadata.setdefault("research_pipeline", research_pipeline.model_dump(mode="json"))
        manifest.metadata.setdefault("research_abstention_policy", research_pipeline.abstention_policy.model_dump(mode="json"))
        manifest.metadata.setdefault("research_abstention_metrics", research_abstention_metrics)
        payload = {
            "run_id": run_id,
            "descriptor": descriptor,
            "market": descriptor,
            "snapshot": snapshot,
            "resolution_policy": resolution,
            "research_findings": research_findings,
            "evidence_packets": evidence_packets,
            "research_synthesis": research_synthesis,
            "research_pipeline": research_pipeline,
            "research_abstention_policy": research_pipeline.abstention_policy,
            "research_abstention_metrics": research_abstention_metrics,
            "comment_intel": comment_report,
            "stream_summary": stream_summary,
            "stream_health": stream_health,
            "manipulation_guard": report,
            "manifest": manifest,
        }
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def reconcile(
        self,
        run_id: str,
        *,
        persist: bool = True,
    ) -> dict[str, Any]:
        manifest = self.registry.load_manifest(run_id)
        artifact_paths = dict(manifest.artifact_paths)
        descriptor = None
        descriptor_path = artifact_paths.get("descriptor")
        if descriptor_path and Path(descriptor_path).exists():
            descriptor = MarketDescriptor.model_validate(load_json(descriptor_path))

        theoretical_ledger = None
        observed_ledger = None
        paper_trades: list[PaperTradeSimulation] = []
        shadow_executions = []

        capital_before_path = artifact_paths.get("capital_ledger_before")
        if capital_before_path and Path(capital_before_path).exists():
            theoretical_ledger = CapitalLedgerSnapshot.model_validate(load_json(capital_before_path))
        elif artifact_paths.get("capital_ledger_before_store"):
            store_path = Path(artifact_paths["capital_ledger_before_store"])
            if store_path.exists():
                theoretical_ledger = CapitalLedgerStore(paths=self.paths).load_snapshot(store_path.stem)

        capital_after_path = artifact_paths.get("capital_ledger_after")
        if capital_after_path and Path(capital_after_path).exists():
            observed_ledger = CapitalLedgerSnapshot.model_validate(load_json(capital_after_path))
        elif artifact_paths.get("capital_ledger_after_store"):
            store_path = Path(artifact_paths["capital_ledger_after_store"])
            if store_path.exists():
                observed_ledger = CapitalLedgerStore(paths=self.paths).load_snapshot(store_path.stem)

        paper_trade_path = artifact_paths.get("paper_trade")
        if paper_trade_path and Path(paper_trade_path).exists():
            paper_trades.append(PaperTradeSimulation.model_validate(load_json(paper_trade_path)))
        elif artifact_paths.get("paper_trade_store"):
            store_path = Path(artifact_paths["paper_trade_store"])
            if store_path.exists():
                paper_trades.append(PaperTradeStore(paths=self.paths).load(store_path.stem))

        shadow_path = artifact_paths.get("shadow_execution")
        if shadow_path and Path(shadow_path).exists():
            shadow_executions.append(ShadowExecutionResult.model_validate(load_json(shadow_path)))
        elif artifact_paths.get("shadow_execution_store"):
            store_path = Path(artifact_paths["shadow_execution_store"])
            if store_path.exists():
                shadow_executions.append(ShadowExecutionStore(paths=self.paths).load(store_path.stem))

        if theoretical_ledger is None:
            theoretical_ledger = CapitalLedger.from_cash(
                cash=DEFAULT_LEDGER_CASH,
                venue=manifest.venue,
                metadata={"market_id": manifest.market_id, "run_id": run_id, "source": "reconciliation_default"},
            ).current_snapshot()

        report = ReconciliationEngine().reconcile(
            theoretical_ledger,
            paper_trades=paper_trades,
            shadow_executions=shadow_executions,
            observed_ledger=observed_ledger,
            run_id=run_id,
            market_id=manifest.market_id,
            venue=manifest.venue,
            persist=persist,
            store=ReconciliationStore(self.paths),
            metadata={"mode": manifest.mode},
        )
        payload = {
            "run_id": run_id,
            "descriptor": descriptor,
            "market": descriptor,
            "theoretical_ledger_snapshot": theoretical_ledger,
            "observed_ledger_snapshot": observed_ledger,
            "reconciliation": report,
            "manifest": manifest,
        }
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def allocate(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        evidence_inputs: list[str] | None = None,
        decision_packet: Any | None = None,
        stake: float = 10.0,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        payload = self._trade_context(
            market_id=market_id,
            slug=slug,
            evidence_inputs=evidence_inputs,
            decision_packet=decision_packet,
            persist=persist,
            run_id=run_id,
            stake=stake,
            mode="allocate",
        )
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def forecast_market(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        evidence_inputs: list[str] | None = None,
        decision_packet: Any | None = None,
        use_social_core: bool = False,
        persist: bool = True,
        run_id: str | None = None,
        mode: str = "forecast",
    ) -> dict[str, Any]:
        forecast_run_id = run_id or _generate_run_id()
        baseline = self.advise(
            market_id=market_id,
            slug=slug,
            evidence_inputs=evidence_inputs,
            decision_packet=decision_packet,
            use_social_core=False,
            persist=False,
            record_evidence=False,
            run_id=forecast_run_id,
            mode=mode,
        )
        social = baseline
        if use_social_core:
            social = self.advise(
                market_id=market_id,
                slug=slug,
                evidence_inputs=evidence_inputs,
                decision_packet=decision_packet,
                use_social_core=True,
                persist=False,
                record_evidence=False,
                run_id=forecast_run_id,
                mode=mode,
            )
        bridge = _social_bridge_metadata(decision_packet)
        comparison = ForecastComparisonSurface(
            run_id=forecast_run_id,
            market_id=baseline["descriptor"].market_id,
            venue=baseline["descriptor"].venue,
            social_core_used=use_social_core,
            base_forecast_id=baseline["forecast"].forecast_id,
            social_forecast_id=social["forecast"].forecast_id if use_social_core else None,
            base_probability_estimate=baseline["forecast"].fair_probability,
            social_probability_estimate=social["forecast"].fair_probability,
            base_edge_after_fees_bps=baseline["forecast"].edge_after_fees_bps,
            social_edge_after_fees_bps=social["forecast"].edge_after_fees_bps,
            base_recommendation_action=baseline["forecast"].recommendation_action,
            social_recommendation_action=social["forecast"].recommendation_action,
            base_requires_manual_review=baseline["forecast"].manual_review_required,
            social_requires_manual_review=social["forecast"].manual_review_required,
            social_bridge_probability=social["forecast"].social_bridge_probability,
            social_bridge_delta_bps=social["forecast"].social_bridge_delta_bps,
            social_bridge_refs=list((bridge or {}).get("source_packet_refs") or []),
            metadata={
                "market_title": baseline["descriptor"].title,
                "baseline_rationale_summary": baseline["forecast"].rationale_summary,
                "social_rationale_summary": social["forecast"].rationale_summary,
                "use_social_core": use_social_core,
                "social_bridge": bridge,
            },
        )
        payload: dict[str, Any] = {
            "run_id": forecast_run_id,
            "descriptor": baseline["descriptor"],
            "snapshot": baseline["snapshot"],
            "baseline_forecast": baseline["forecast"],
            "social_forecast": social["forecast"],
            "comparison": comparison,
            "decision_packet": _normalize_decision_packet(decision_packet),
            "use_social_core": use_social_core,
        }
        if persist:
            forecast_dir = _run_artifact_path(self.paths, forecast_run_id, "forecast_comparison.json")
            forecast_dir.write_text(comparison.model_dump_json(indent=2), encoding="utf-8")
            payload["comparison_path"] = str(forecast_dir)
        return payload

    def paper_trade(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        evidence_inputs: list[str] | None = None,
        decision_packet: Any | None = None,
        stake: float = 10.0,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        payload = self._trade_context(
            market_id=market_id,
            slug=slug,
            evidence_inputs=evidence_inputs,
            decision_packet=decision_packet,
            persist=persist,
            run_id=run_id,
            stake=stake,
            mode="paper",
        )
        recommendation: MarketRecommendationPacket = payload["recommendation"]
        snapshot: MarketSnapshot = payload["snapshot"]
        allocation: AllocationDecision = payload["allocation"]
        ledger_before: CapitalLedgerSnapshot = payload["capital_ledger_before"]
        projection: ExecutionProjection = payload["execution_projection"]
        effective_allocation = allocation
        if projection.projected_mode == ExecutionProjectionOutcome.blocked:
            effective_allocation = allocation.model_copy(
                update={
                    "should_trade": False,
                    "recommended_stake": 0.0,
                    "no_trade_reasons": list(
                        dict.fromkeys(
                            [*allocation.no_trade_reasons, *projection.blocking_reasons]
                            or ["execution_projection_blocked"]
                        )
                    ),
                }
            )
        paper_trade, ledger_after, ledger_change = _simulate_paper_trade_payload(
            run_id=payload["run_id"],
            descriptor=payload["descriptor"],
            snapshot=snapshot,
            recommendation=recommendation,
            allocation=effective_allocation,
            risk_report=payload["risk_report"],
            ledger_before=ledger_before,
            metadata={
                "allocation_id": allocation.allocation_id,
                "execution_projection_id": projection.projection_id,
                "requested_mode": projection.requested_mode.value,
                "projected_mode": projection.projected_mode.value,
            },
        )
        payload["paper_trade"] = paper_trade
        payload["capital_ledger_after"] = ledger_after
        payload["capital_ledger_change"] = ledger_change
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def shadow_trade(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        evidence_inputs: list[str] | None = None,
        decision_packet: Any | None = None,
        stake: float = 10.0,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        payload = self._trade_context(
            market_id=market_id,
            slug=slug,
            evidence_inputs=evidence_inputs,
            decision_packet=decision_packet,
            persist=persist,
            run_id=run_id,
            stake=stake,
            mode="shadow",
        )
        recommendation: MarketRecommendationPacket = payload["recommendation"]
        allocation: AllocationDecision = payload["allocation"]
        ledger_before: CapitalLedgerSnapshot = payload["capital_ledger_before"]
        projection: ExecutionProjection = payload["execution_projection"]
        effective_recommendation = recommendation
        effective_stake = allocation.recommended_stake if allocation.should_trade else 0.0
        if not allocation.should_trade or projection.projected_mode == ExecutionProjectionOutcome.blocked:
            effective_recommendation = recommendation.model_copy(update={"action": DecisionAction.no_trade, "side": None})
        if projection.projected_mode == ExecutionProjectionOutcome.paper:
            paper_trade, ledger_after, ledger_change = _simulate_paper_trade_payload(
                run_id=payload["run_id"],
                descriptor=payload["descriptor"],
                snapshot=payload["snapshot"],
                recommendation=recommendation,
                allocation=allocation,
                risk_report=payload["risk_report"],
                ledger_before=ledger_before,
                metadata={
                    "shadow_degraded_to": "paper",
                    "execution_projection_id": projection.projection_id,
                    "requested_mode": projection.requested_mode.value,
                    "projected_mode": projection.projected_mode.value,
                },
            )
            shadow_execution = ShadowExecutionResult(
                run_id=payload["run_id"],
                market_id=payload["descriptor"].market_id,
                venue=payload["descriptor"].venue,
                recommendation_id=recommendation.recommendation_id,
                would_trade=False,
                blocked_reason="execution_projection_degraded_to_paper",
                paper_trade=paper_trade,
                ledger_before=ledger_before,
                ledger_after=ledger_after,
                ledger_change=ledger_change,
                risk_flags=["projection_degraded_to_paper"],
                metadata={
                    "execution_projection_id": projection.projection_id,
                    "requested_mode": projection.requested_mode.value,
                    "projected_mode": projection.projected_mode.value,
                },
            )
            if persist:
                shadow_store = ShadowExecutionStore(self.paths)
                shadow_store.save(shadow_execution)
                if paper_trade is not None:
                    PaperTradeStore(shadow_store.paths).save(paper_trade)
                CapitalLedgerStore(shadow_store.paths).save_snapshot(ledger_after)
        else:
            shadow_execution = ShadowExecutionEngine(
                starting_cash=ledger_before.cash,
                default_stake=max(effective_stake, 0.0),
            ).run(
                effective_recommendation,
                payload["snapshot"],
                ledger=ledger_before,
                stake=max(effective_stake, 0.0),
                persist=persist,
                store=ShadowExecutionStore(self.paths),
            )
            shadow_execution = shadow_execution.model_copy(
                update={
                    "metadata": {
                        **dict(shadow_execution.metadata),
                        "execution_projection_id": projection.projection_id,
                        "requested_mode": projection.requested_mode.value,
                        "projected_mode": projection.projected_mode.value,
                    }
                }
            )
        payload["shadow_execution"] = shadow_execution
        payload["paper_trade"] = shadow_execution.paper_trade
        payload["capital_ledger_after"] = shadow_execution.ledger_after
        payload["capital_ledger_change"] = shadow_execution.ledger_change
        payload["shadow_postmortem"] = _shadow_postmortem_surface(shadow_execution)
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def comment_intel(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        comments: list[str] | None = None,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        descriptor = _resolve_market(self.client, market_id=market_id, slug=slug)
        report = MarketCommentIntel().analyze(
            [CommentRecord(text=item) for item in (comments or [])],
            market_id=descriptor.market_id,
            venue=descriptor.venue,
            market_title=descriptor.title,
            market_question=descriptor.question,
        )
        run_id = run_id or _generate_run_id("pm_comment")
        manifest = RunManifest(
            run_id=run_id,
            venue=descriptor.venue,
            venue_type=descriptor.venue_type,
            market_id=descriptor.market_id,
            mode="comment_intel",
            inputs={"slug": descriptor.slug, "market_id": descriptor.market_id, "comment_count": len(comments or [])},
        )
        payload = {"run_id": run_id, "descriptor": descriptor, "market": descriptor, "comment_intel": report, "manifest": manifest}
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def market_graph(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        limit: int = 12,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        descriptor = _resolve_market(self.client, market_id=market_id, slug=slug)
        markets = _load_market_pool(self.client, descriptor, limit=limit)
        snapshots = {market.market_id: _resolve_snapshot(self.client, market) for market in markets}
        graph = MarketGraphBuilder().build(markets, snapshots=snapshots)
        run_id = run_id or _generate_run_id("pm_graph")
        manifest = RunManifest(
            run_id=run_id,
            venue=descriptor.venue,
            venue_type=descriptor.venue_type,
            market_id=descriptor.market_id,
            mode="graph",
            inputs={"slug": descriptor.slug, "market_id": descriptor.market_id, "limit": limit},
        )
        payload = {
            "run_id": run_id,
            "descriptor": descriptor,
            "market": descriptor,
            "markets": markets,
            "market_graph": graph,
            "manifest": manifest,
        }
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def cross_venue(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        limit: int = 12,
        include_additional_venues: bool = False,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        descriptor = _resolve_market(self.client, market_id=market_id, slug=slug)
        markets, snapshots, additional_venues_matrix, additional_venue_profiles = self._build_market_context(
            descriptor=descriptor,
            include_additional_venues=include_additional_venues,
            limit=limit,
        )
        report = CrossVenueIntelligence().build_report(markets, snapshots=snapshots)
        run_id = run_id or _generate_run_id("pm_cross")
        manifest = RunManifest(
            run_id=run_id,
            venue=descriptor.venue,
            venue_type=descriptor.venue_type,
            market_id=descriptor.market_id,
            mode="cross_venue",
            inputs={
                "slug": descriptor.slug,
                "market_id": descriptor.market_id,
                "limit": limit,
                "include_additional_venues": include_additional_venues,
            },
        )
        payload = {
            "run_id": run_id,
            "descriptor": descriptor,
            "market": descriptor,
            "market_pool": markets,
            "cross_venue": report,
            "additional_venues_matrix": additional_venues_matrix,
            "additional_venue_profiles": additional_venue_profiles,
            "manifest": manifest,
        }
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def multi_venue_execution(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        limit: int = 12,
        include_additional_venues: bool = True,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        descriptor = _resolve_market(self.client, market_id=market_id, slug=slug)
        markets, snapshots, additional_venues_matrix, additional_venue_profiles = self._build_market_context(
            descriptor=descriptor,
            include_additional_venues=include_additional_venues,
            limit=limit,
        )
        report = build_multi_venue_execution_report(markets, snapshots=snapshots)
        run_id = run_id or _generate_run_id("pm_multi_exec")
        manifest = RunManifest(
            run_id=run_id,
            venue=descriptor.venue,
            venue_type=descriptor.venue_type,
            market_id=descriptor.market_id,
            mode="multi_venue_execution",
            inputs={
                "slug": descriptor.slug,
                "market_id": descriptor.market_id,
                "limit": limit,
                "include_additional_venues": include_additional_venues,
            },
        )
        payload = {
            "run_id": run_id,
            "descriptor": descriptor,
            "market": descriptor,
            "market_pool": markets,
            "cross_venue": report.cross_venue_report,
            "multi_venue_execution": report,
            "additional_venues_matrix": additional_venues_matrix,
            "additional_venue_profiles": additional_venue_profiles,
            "manifest": manifest,
        }
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def multi_venue_paper(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        limit: int = 12,
        include_additional_venues: bool = True,
        persist: bool = True,
        run_id: str | None = None,
        target_notional_usd: float | None = None,
    ) -> dict[str, Any]:
        descriptor = _resolve_market(self.client, market_id=market_id, slug=slug)
        markets, snapshots, additional_venues_matrix, additional_venue_profiles = self._build_market_context(
            descriptor=descriptor,
            include_additional_venues=include_additional_venues,
            limit=limit,
        )
        execution_report = build_multi_venue_execution_report(
            markets,
            snapshots=snapshots,
            target_notional_usd=target_notional_usd or 1000.0,
        )
        paper_report = build_multi_venue_paper_report(
            markets,
            execution_report=execution_report,
            snapshots=snapshots,
            target_notional_usd=target_notional_usd,
        )
        run_id = run_id or _generate_run_id("pm_multi_paper")
        manifest = RunManifest(
            run_id=run_id,
            venue=descriptor.venue,
            venue_type=descriptor.venue_type,
            market_id=descriptor.market_id,
            mode="multi_venue_paper",
            inputs={
                "slug": descriptor.slug,
                "market_id": descriptor.market_id,
                "limit": limit,
                "include_additional_venues": include_additional_venues,
                "target_notional_usd": target_notional_usd,
            },
        )
        payload = {
            "run_id": run_id,
            "descriptor": descriptor,
            "market": descriptor,
            "market_pool": markets,
            "cross_venue": execution_report.cross_venue_report,
            "multi_venue_execution": execution_report,
            "multi_venue_paper": paper_report,
            "additional_venues_matrix": additional_venues_matrix,
            "additional_venue_profiles": additional_venue_profiles,
            "manifest": manifest,
        }
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def spread_monitor(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        limit: int = 12,
        include_additional_venues: bool = True,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        descriptor = _resolve_market(self.client, market_id=market_id, slug=slug)
        markets, snapshots, additional_venues_matrix, additional_venue_profiles = self._build_market_context(
            descriptor=descriptor,
            include_additional_venues=include_additional_venues,
            limit=limit,
        )
        report = monitor_spreads(markets, snapshots=snapshots)
        run_id = run_id or _generate_run_id("pm_spread")
        manifest = RunManifest(
            run_id=run_id,
            venue=descriptor.venue,
            venue_type=descriptor.venue_type,
            market_id=descriptor.market_id,
            mode="spread_monitor",
            inputs={
                "slug": descriptor.slug,
                "market_id": descriptor.market_id,
                "limit": limit,
                "include_additional_venues": include_additional_venues,
            },
        )
        payload = {
            "run_id": run_id,
            "descriptor": descriptor,
            "market": descriptor,
            "snapshot": snapshots.get(descriptor.market_id),
            "market_pool": markets,
            "spread_monitor": report,
            "additional_venues_matrix": additional_venues_matrix,
            "additional_venue_profiles": additional_venue_profiles,
            "manifest": manifest,
        }
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def arbitrage_lab(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        limit: int = 12,
        include_additional_venues: bool = True,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        descriptor = _resolve_market(self.client, market_id=market_id, slug=slug)
        markets, snapshots, additional_venues_matrix, additional_venue_profiles = self._build_market_context(
            descriptor=descriptor,
            include_additional_venues=include_additional_venues,
            limit=limit,
        )
        report = assess_arbitrage(markets, snapshots=snapshots)
        run_id = run_id or _generate_run_id("pm_arb")
        manifest = RunManifest(
            run_id=run_id,
            venue=descriptor.venue,
            venue_type=descriptor.venue_type,
            market_id=descriptor.market_id,
            mode="arbitrage_lab",
            inputs={
                "slug": descriptor.slug,
                "market_id": descriptor.market_id,
                "limit": limit,
                "include_additional_venues": include_additional_venues,
            },
        )
        payload = {
            "run_id": run_id,
            "descriptor": descriptor,
            "market": descriptor,
            "snapshot": snapshots.get(descriptor.market_id),
            "market_pool": markets,
            "arbitrage_lab": report,
            "additional_venues_matrix": additional_venues_matrix,
            "additional_venue_profiles": additional_venue_profiles,
            "manifest": manifest,
        }
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def live_execute(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        evidence_inputs: list[str] | None = None,
        decision_packet: dict[str, Any] | None = None,
        stake: float = 10.0,
        persist: bool = True,
        run_id: str | None = None,
        dry_run: bool = True,
        allow_live_execution: bool = False,
        authorized: bool = False,
        compliance_approved: bool = False,
        principal: str = "",
        scopes: list[str] | None = None,
        require_human_approval_before_live: bool = False,
        human_approval_passed: bool = False,
        human_approval_actor: str = "",
        human_approval_reason: str = "",
    ) -> dict[str, Any]:
        payload = self._trade_context(
            market_id=market_id,
            slug=slug,
            evidence_inputs=evidence_inputs,
            decision_packet=decision_packet,
            persist=persist,
            run_id=run_id,
            stake=stake,
            mode="live_execution",
        )
        allocation: AllocationDecision = payload["allocation"]
        effective_stake = allocation.recommended_stake if allocation.should_trade else 0.0
        auth = ExecutionAuthContext(
            principal=principal,
            authorized=authorized,
            compliance_approved=compliance_approved,
            scopes=scopes or [],
        )
        request = LiveExecutionRequest(
            run_id=payload["run_id"],
            market=payload["descriptor"],
            snapshot=payload["snapshot"],
            recommendation=payload["recommendation"],
            requested_mode="live" if allow_live_execution and not dry_run else "paper",
            ledger=payload["capital_ledger_before"],
            risk_report=payload["risk_report"],
            requested_stake=max(stake, effective_stake),
            dry_run=dry_run,
            auth=auth,
            metadata={
                "allocation_id": allocation.allocation_id,
                "trade_intent_id": payload["trade_intent"].intent_id if isinstance(payload.get("trade_intent"), TradeIntent) else None,
                "human_approval_passed": human_approval_passed,
                "human_approval_actor": human_approval_actor,
                "human_approval_reason": human_approval_reason,
                "authorized": authorized,
                "compliance_approved": compliance_approved,
                "auth_principal": principal,
                "auth_scopes": list(scopes or []),
                "social_bridge_available": bool(payload["forecast"].metadata.get("social_bridge")),
                "social_bridge_state": "available" if payload["forecast"].metadata.get("social_bridge") else "unavailable",
                "social_bridge_runbook": _social_bridge_runbook(payload["forecast"].metadata.get("social_bridge")),
                "manipulation_guard_id": payload["manipulation_guard"].guard_id if isinstance(payload.get("manipulation_guard"), ManipulationGuardReport) else None,
                "manipulation_guard_severity": payload["manipulation_guard"].severity.value if isinstance(payload.get("manipulation_guard"), ManipulationGuardReport) else None,
                "manipulation_guard_signal_only": payload["manipulation_guard"].signal_only if isinstance(payload.get("manipulation_guard"), ManipulationGuardReport) else False,
                "manipulation_suspicion": bool(isinstance(payload.get("manipulation_guard"), ManipulationGuardReport) and (payload["manipulation_guard"].signal_only or payload["manipulation_guard"].severity.value in {"medium", "high", "critical"})),
            },
        )
        venue_order_submitters, venue_order_cancel_submitters = _build_default_live_execution_transport_bindings()
        record = LiveExecutionEngine(
            policy=LiveExecutionPolicy(
                dry_run_enabled=dry_run,
                allow_live_execution=allow_live_execution,
                require_human_approval_before_live=require_human_approval_before_live,
                allowed_venues={payload["descriptor"].venue},
            ),
            venue_order_submitters=venue_order_submitters,
            venue_order_cancel_submitters=venue_order_cancel_submitters,
        ).execute(
            request,
            persist=persist,
            store=LiveExecutionStore(self.paths),
            ledger_store=CapitalLedgerStore(self.paths),
            paper_trade_store=PaperTradeStore(self.paths),
        )
        payload["live_execution"] = record
        payload["market_execution"] = MarketExecutionEngine().materialize(
            record,
            trade_intent=payload.get("trade_intent"),
            ledger_after=record.ledger_after,
            persist=persist,
            store=MarketExecutionStore(self.paths),
        )
        order_trace_audit = _order_trace_audit_from_payload(record, payload["market_execution"])
        if order_trace_audit is not None:
            payload["order_trace_audit"] = order_trace_audit
            payload["live_execution"].metadata["order_trace_audit"] = order_trace_audit
            payload["market_execution"].metadata["order_trace_audit"] = order_trace_audit
            payload["market_execution"].order.metadata["order_trace_audit"] = order_trace_audit
            manifest = payload.get("manifest")
            if manifest is not None and hasattr(manifest, "metadata"):
                manifest.metadata = {**dict(manifest.metadata or {}), "order_trace_audit": order_trace_audit}
        payload["paper_trade"] = record.paper_trade
        payload["capital_ledger_after"] = record.ledger_after
        payload["capital_ledger_change"] = record.ledger_change
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def market_execution(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        evidence_inputs: list[str] | None = None,
        decision_packet: dict[str, Any] | None = None,
        stake: float = 10.0,
        persist: bool = True,
        run_id: str | None = None,
        dry_run: bool = True,
        allow_live_execution: bool = False,
        authorized: bool = False,
        compliance_approved: bool = False,
        principal: str = "",
        scopes: list[str] | None = None,
        require_human_approval_before_live: bool = False,
        human_approval_passed: bool = False,
        human_approval_actor: str = "",
        human_approval_reason: str = "",
    ) -> dict[str, Any]:
        return self.live_execute(
            market_id=market_id,
            slug=slug,
            evidence_inputs=evidence_inputs,
            decision_packet=decision_packet,
            stake=stake,
            persist=persist,
            run_id=run_id,
            dry_run=dry_run,
            allow_live_execution=allow_live_execution,
            authorized=authorized,
            compliance_approved=compliance_approved,
            principal=principal,
            scopes=scopes,
            require_human_approval_before_live=require_human_approval_before_live,
            human_approval_passed=human_approval_passed,
            human_approval_actor=human_approval_actor,
            human_approval_reason=human_approval_reason,
        )

    def worldmonitor_sidecar(
        self,
        source: Any,
        *,
        market_id: str | None = None,
        slug: str | None = None,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        descriptor = _resolve_market(self.client, market_id=market_id, slug=slug) if market_id or slug else None
        run_id = run_id or _generate_run_id("pm_world")
        bundle = WorldMonitorSidecarBridge().ingest(
            source,
            market_id=descriptor.market_id if descriptor is not None else market_id,
            venue=descriptor.venue if descriptor is not None else VenueName.polymarket,
            run_id=run_id,
        )
        research_bridge = build_sidecar_research_bundle(
            bundle.findings,
            market_id=bundle.market_id,
            venue=bundle.venue,
            run_id=run_id,
            sidecar_name=bundle.sidecar_name,
            sidecar_health=bundle.health.model_dump(mode="json"),
            classification=bundle.metadata.get("classification", "signal"),
            classification_reasons=list(bundle.metadata.get("classification_reasons", [])),
            source_path=bundle.source_path,
        )
        self._record_evidence_packets(
            bundle.evidence,
            run_id=run_id,
            market_id=bundle.market_id,
            source_type="worldmonitor_sidecar",
            classification=bundle.metadata.get("classification", "signal"),
            source_path=bundle.source_path,
        )
        manifest = RunManifest(
            run_id=run_id,
            venue=descriptor.venue if descriptor is not None else bundle.venue,
            venue_type=descriptor.venue_type if descriptor is not None else VenueType.reference,
            market_id=descriptor.market_id if descriptor is not None else bundle.market_id,
            mode="worldmonitor_sidecar",
            inputs={"slug": None if descriptor is None else descriptor.slug, "source": str(source)},
        )
        payload = {
            "run_id": run_id,
            "descriptor": descriptor,
            "market": descriptor,
            "research_findings": bundle.findings,
            "evidence_packets": bundle.evidence,
            "research_bridge": research_bridge,
            "worldmonitor_sidecar": bundle,
            "manifest": manifest,
        }
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def twitter_watcher_sidecar(
        self,
        source: Any,
        *,
        market_id: str | None = None,
        slug: str | None = None,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        descriptor = _resolve_market(self.client, market_id=market_id, slug=slug) if market_id or slug else None
        run_id = run_id or _generate_run_id("pm_twitter")
        bundle = TwitterWatcherSidecarBridge().ingest(
            source,
            market_id=descriptor.market_id if descriptor is not None else market_id,
            venue=descriptor.venue if descriptor is not None else VenueName.polymarket,
            run_id=run_id,
        )
        research_bridge = build_sidecar_research_bundle(
            bundle.findings,
            market_id=bundle.market_id,
            venue=bundle.venue,
            run_id=run_id,
            sidecar_name=bundle.sidecar_name,
            sidecar_health=bundle.health.model_dump(mode="json"),
            classification=bundle.metadata.get("classification", "signal"),
            classification_reasons=list(bundle.metadata.get("classification_reasons", [])),
            source_path=bundle.source_path,
        )
        self._record_evidence_packets(
            bundle.evidence,
            run_id=run_id,
            market_id=bundle.market_id,
            source_type="twitter_watcher_sidecar",
            classification=bundle.metadata.get("classification", "signal"),
            source_path=bundle.source_path,
        )
        manifest = RunManifest(
            run_id=run_id,
            venue=descriptor.venue if descriptor is not None else bundle.venue,
            venue_type=descriptor.venue_type if descriptor is not None else VenueType.signal,
            market_id=descriptor.market_id if descriptor is not None else bundle.market_id,
            mode="twitter_watcher_sidecar",
            inputs={"slug": None if descriptor is None else descriptor.slug, "source": str(source)},
        )
        payload = {
            "run_id": run_id,
            "descriptor": descriptor,
            "market": descriptor,
            "research_findings": bundle.findings,
            "evidence_packets": bundle.evidence,
            "research_bridge": research_bridge,
            "twitter_watcher_sidecar": bundle,
            "manifest": manifest,
        }
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def additional_venues_catalog(
        self,
        *,
        query: str | None = None,
        limit_per_venue: int = 2,
        persist: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        registry = self.additional_venues
        matrix = registry.describe_matrix()
        venue_profiles = registry.list_profiles()
        markets: list[MarketDescriptor] = []
        for venue in registry.list_venues():
            config = MarketUniverseConfig(venue=venue, query=query, limit=limit_per_venue)
            _append_unique_markets(markets, registry.list_markets(venue, config=config, limit=limit_per_venue))
        run_id = run_id or _generate_run_id("pm_venues")
        manifest = RunManifest(
            run_id=run_id,
            venue=VenueName.polymarket,
            venue_type=VenueType.reference,
            market_id=query or "additional_venues",
            mode="additional_venues",
            inputs={"query": query, "limit_per_venue": limit_per_venue},
        )
        payload = {
            "run_id": run_id,
            "additional_venues_matrix": matrix,
            "additional_venue_profiles": venue_profiles,
            "market_pool": markets,
            "manifest": manifest,
        }
        if persist:
            self._persist_extended_artifacts(payload)
        return payload

    def stream_open(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        poll_count: int = 1,
    ) -> dict[str, Any]:
        streamer = MarketStreamer(client=self.client, backend_mode=self.backend_mode, paths=self.paths)
        session = streamer.open(market_id=market_id, slug=slug)
        events = session.poll_many(count=max(1, poll_count))
        return {
            "stream_id": session.stream_id,
            "descriptor": session.descriptor,
            "market": session.descriptor,
            "stream_manifest": session.manifest,
            "events": events,
            "stream_summary": session.summarize(),
            "stream_health": session.health(),
        }

    def stream_summary(self, stream_id: str) -> dict[str, Any]:
        streamer = MarketStreamer(client=self.client, backend_mode=self.backend_mode, paths=self.paths)
        summary = streamer.summarize(stream_id)
        return {"stream_id": stream_id, "stream_summary": summary}

    def stream_health(self, stream_id: str, *, stale_after_seconds: float = 3600.0) -> dict[str, Any]:
        streamer = MarketStreamer(client=self.client, backend_mode=self.backend_mode, paths=self.paths)
        health = streamer.health(stream_id, stale_after_seconds=stale_after_seconds)
        return {"stream_id": stream_id, "stream_health": health}

    def stream_collect(
        self,
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
        priority_strategy: StreamCollectionPriority | str = StreamCollectionPriority.freshness,
        poll_count: int = 1,
        stale_after_seconds: float = 3600.0,
    ) -> dict[str, Any]:
        report = collect_market_streams(
            market_ids=market_ids,
            slugs=slugs,
            stream_ids=stream_ids,
            fanout=fanout,
            retries=retries,
            timeout_seconds=timeout_seconds,
            cache_ttl_seconds=cache_ttl_seconds,
            prefetch=prefetch,
            backpressure_limit=backpressure_limit,
            priority_strategy=priority_strategy if isinstance(priority_strategy, StreamCollectionPriority) else StreamCollectionPriority(str(priority_strategy)),
            poll_count=poll_count,
            stale_after_seconds=stale_after_seconds,
            client=self.client,
            backend_mode=self.backend_mode,
            paths=self.paths,
        )
        return {
            "stream_collection": report,
            "report": report,
        }

    def venue_health(
        self,
        *,
        venue: VenueName | None = None,
        market_id: str | None = None,
        slug: str | None = None,
        stream_id: str | None = None,
        stale_after_seconds: float = 3600.0,
    ) -> dict[str, Any]:
        target_venue = venue
        descriptor = None
        if target_venue is None and (market_id is not None or slug is not None):
            descriptor = _resolve_market(self.client, market_id=market_id, slug=slug)
            target_venue = descriptor.venue
        if target_venue is None:
            target_venue = getattr(self.client, "venue", VenueName.polymarket)
        venue_health = _venue_health_report(
            venue=target_venue,
            backend_mode=self.backend_mode,
            client=self.client,
        )
        stream_health = None
        if stream_id is not None:
            streamer = MarketStreamer(client=self.client, backend_mode=self.backend_mode, paths=self.paths)
            stream_health = streamer.health(stream_id, stale_after_seconds=stale_after_seconds)
        combined_issues = list(venue_health.details.get("issues", []))
        if stream_health is not None:
            combined_issues.extend(stream_health.issues)
        combined_issues = sorted(set(combined_issues))
        overall_healthy = venue_health.healthy and (stream_health.healthy if stream_health is not None else True)
        return {
            "venue": target_venue,
            "descriptor": descriptor,
            "venue_health": venue_health,
            "stream_health": stream_health,
            "healthy": overall_healthy,
            "issues": combined_issues,
        }


def advise_market_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence_inputs: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    use_social_core: bool = False,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.advise(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence_inputs,
        decision_packet=decision_packet,
        use_social_core=use_social_core,
        persist=persist,
    )


def forecast_market_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence_inputs: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    use_social_core: bool = False,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.forecast_market(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence_inputs,
        decision_packet=decision_packet,
        use_social_core=use_social_core,
        persist=persist,
    )


def paper_trade_market_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence_inputs: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    stake: float = 10.0,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    preflight = advisor.advise(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence_inputs,
        decision_packet=decision_packet,
        persist=False,
        mode="paper",
    )
    paper_trade_guard = _paper_trade_guard(preflight)
    if paper_trade_guard["paper_trade_blocked"]:
        payload = preflight.model_dump(mode="json") if hasattr(preflight, "model_dump") else dict(preflight)
        payload["paper_trade"] = None
        payload["paper_trade_guard"] = paper_trade_guard
        payload["paper_trade_blocked"] = True
        payload["paper_trade_blocked_reasons"] = paper_trade_guard["paper_trade_blocked_reasons"]
        payload["paper_trade_blocked_reason"] = paper_trade_guard["paper_trade_blocked_reason"]
        return payload

    payload = advisor.paper_trade(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence_inputs,
        decision_packet=decision_packet,
        stake=stake,
        persist=persist,
    )
    payload["paper_trade_guard"] = paper_trade_guard
    payload["paper_trade_blocked"] = False
    payload["paper_trade_blocked_reasons"] = []
    payload["paper_trade_blocked_reason"] = ""
    return payload


def assess_market_risk_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence_inputs: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    stake: float = 10.0,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.risk(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence_inputs,
        decision_packet=decision_packet,
        stake=stake,
        persist=persist,
    )


def allocate_market_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence_inputs: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    stake: float = 10.0,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.allocate(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence_inputs,
        decision_packet=decision_packet,
        stake=stake,
        persist=persist,
    )


def shadow_trade_market_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence_inputs: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    stake: float = 10.0,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.shadow_trade(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence_inputs,
        decision_packet=decision_packet,
        stake=stake,
        persist=persist,
    )


def analyze_market_comments_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    comments: list[str] | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.comment_intel(
        market_id=market_id,
        slug=slug,
        comments=comments,
        persist=persist,
    )


def build_market_graph_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    limit: int = 12,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.market_graph(
        market_id=market_id,
        slug=slug,
        limit=limit,
        persist=persist,
    )


def cross_venue_intelligence_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    limit: int = 12,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.cross_venue(
        market_id=market_id,
        slug=slug,
        limit=limit,
        persist=persist,
    )


def multi_venue_execution_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    limit: int = 12,
    include_additional_venues: bool = True,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.multi_venue_execution(
        market_id=market_id,
        slug=slug,
        limit=limit,
        include_additional_venues=include_additional_venues,
        persist=persist,
    )


def multi_venue_paper_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    limit: int = 12,
    include_additional_venues: bool = True,
    target_notional_usd: float | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.multi_venue_paper(
        market_id=market_id,
        slug=slug,
        limit=limit,
        include_additional_venues=include_additional_venues,
        target_notional_usd=target_notional_usd,
        persist=persist,
    )


def monitor_market_spreads_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    limit: int = 12,
    include_additional_venues: bool = True,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.spread_monitor(
        market_id=market_id,
        slug=slug,
        limit=limit,
        include_additional_venues=include_additional_venues,
        persist=persist,
    )


def assess_market_arbitrage_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    limit: int = 12,
    include_additional_venues: bool = True,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.arbitrage_lab(
        market_id=market_id,
        slug=slug,
        limit=limit,
        include_additional_venues=include_additional_venues,
        persist=persist,
    )


def research_market_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence_inputs: list[str] | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.research(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence_inputs,
        persist=persist,
    )


def simulate_market_slippage_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    position_side: TradeSide = TradeSide.yes,
    execution_side: TradeSide = TradeSide.buy,
    requested_quantity: float | None = None,
    requested_notional: float | None = None,
    limit_price: float | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.slippage(
        market_id=market_id,
        slug=slug,
        position_side=position_side,
        execution_side=execution_side,
        requested_quantity=requested_quantity,
        requested_notional=requested_notional,
        limit_price=limit_price,
        persist=persist,
    )


def simulate_microstructure_lab_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    position_side: TradeSide = TradeSide.yes,
    execution_side: TradeSide = TradeSide.buy,
    requested_quantity: float,
    capital_available_usd: float | None = None,
    capital_locked_usd: float = 0.0,
    queue_ahead_quantity: float = 0.0,
    spread_collapse_threshold_bps: float = 50.0,
    collapse_liquidity_multiplier: float = 0.35,
    limit_price: float | None = None,
    fee_bps: float = 0.0,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.microstructure(
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
    )


def guard_market_manipulation_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence_inputs: list[str] | None = None,
    comments: list[str] | None = None,
    poll_count: int = 0,
    stale_after_seconds: float = 3600.0,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.manipulation_guard(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence_inputs,
        comments=comments,
        poll_count=poll_count,
        stale_after_seconds=stale_after_seconds,
        persist=persist,
    )


def live_execute_market_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence_inputs: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    stake: float = 10.0,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
    dry_run: bool = True,
    allow_live_execution: bool = False,
    authorized: bool = False,
    compliance_approved: bool = False,
    principal: str = "",
    scopes: list[str] | None = None,
    require_human_approval_before_live: bool = False,
    human_approval_passed: bool = False,
    human_approval_actor: str = "",
    human_approval_reason: str = "",
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.live_execute(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence_inputs,
        decision_packet=decision_packet,
        stake=stake,
        persist=persist,
        dry_run=dry_run,
        allow_live_execution=allow_live_execution,
        authorized=authorized,
        compliance_approved=compliance_approved,
        principal=principal,
        scopes=scopes,
        require_human_approval_before_live=require_human_approval_before_live,
        human_approval_passed=human_approval_passed,
        human_approval_actor=human_approval_actor,
        human_approval_reason=human_approval_reason,
    )


def market_execution_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence_inputs: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    stake: float = 10.0,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
    dry_run: bool = True,
    allow_live_execution: bool = False,
    authorized: bool = False,
    compliance_approved: bool = False,
    principal: str = "",
    scopes: list[str] | None = None,
    require_human_approval_before_live: bool = False,
    human_approval_passed: bool = False,
    human_approval_actor: str = "",
    human_approval_reason: str = "",
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.market_execution(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence_inputs,
        decision_packet=decision_packet,
        stake=stake,
        persist=persist,
        dry_run=dry_run,
        allow_live_execution=allow_live_execution,
        authorized=authorized,
        compliance_approved=compliance_approved,
        principal=principal,
        scopes=scopes,
        require_human_approval_before_live=require_human_approval_before_live,
        human_approval_passed=human_approval_passed,
        human_approval_actor=human_approval_actor,
        human_approval_reason=human_approval_reason,
    )


def ingest_worldmonitor_sidecar_sync(
    source: Any,
    *,
    market_id: str | None = None,
    slug: str | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.worldmonitor_sidecar(
        source,
        market_id=market_id,
        slug=slug,
        persist=persist,
    )


def ingest_twitter_watcher_sidecar_sync(
    source: Any,
    *,
    market_id: str | None = None,
    slug: str | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.twitter_watcher_sidecar(
        source,
        market_id=market_id,
        slug=slug,
        persist=persist,
    )


def additional_venues_catalog_sync(
    *,
    query: str | None = None,
    limit_per_venue: int = 2,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.additional_venues_catalog(
        query=query,
        limit_per_venue=limit_per_venue,
        persist=persist,
    )


def market_events_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    venue: VenueName | str | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.market_events(
        market_id=market_id,
        slug=slug,
        venue=venue,
        persist=persist,
    )


def market_positions_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    venue: VenueName | str | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.market_positions(
        market_id=market_id,
        slug=slug,
        venue=venue,
        persist=persist,
    )


def reconcile_market_run_sync(
    run_id: str,
    *,
    persist: bool = True,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.reconcile(run_id, persist=persist)


def open_market_stream_sync(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    poll_count: int = 1,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.stream_open(
        market_id=market_id,
        slug=slug,
        poll_count=poll_count,
    )


def market_stream_summary_sync(
    stream_id: str,
    *,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.stream_summary(stream_id)


def market_stream_health_sync(
    stream_id: str,
    *,
    stale_after_seconds: float = 3600.0,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.stream_health(stream_id, stale_after_seconds=stale_after_seconds)


def market_data_surface_sync(
    *,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.market_data_surface()


def market_health_surface_sync(
    *,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.market_health_surface()


def stream_collect_sync(
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
    priority_strategy: StreamCollectionPriority | str = StreamCollectionPriority.freshness,
    poll_count: int = 1,
    stale_after_seconds: float = 3600.0,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.stream_collect(
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
    )


def venue_health_sync(
    *,
    venue: VenueName | None = None,
    market_id: str | None = None,
    slug: str | None = None,
    stream_id: str | None = None,
    stale_after_seconds: float = 3600.0,
    backend_mode: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    advisor = PredictionMarketAdvisor(base_dir=base_dir, backend_mode=backend_mode)
    return advisor.venue_health(
        venue=venue,
        market_id=market_id,
        slug=slug,
        stream_id=stream_id,
        stale_after_seconds=stale_after_seconds,
    )


def replay_market_run_sync(run_id: str, *, base_dir: str | Path | None = None) -> dict[str, Any]:
    paths = _prediction_market_paths(base_dir)
    manifest = RunRegistry(paths).load_manifest(run_id)
    descriptor = None
    descriptor_path = manifest.artifact_paths.get("descriptor") if manifest.artifact_paths else None
    if descriptor_path and Path(descriptor_path).exists():
        descriptor = MarketDescriptor.model_validate(load_json(descriptor_path))
    elif manifest.inputs.get("market_id"):
        descriptor = MarketDescriptor(market_id=str(manifest.inputs["market_id"]), title=str(manifest.inputs.get("market_id")))

    snapshot = MarketSnapshot.model_validate(load_json(paths.snapshot_path(run_id)))
    report_path = paths.report_path(run_id)
    report_payload = load_json(report_path) if report_path.exists() else None
    try:
        packets = load_market_packet_bundle(paths, run_id)
    except Exception:
        payload: dict[str, Any] = {
            "run_id": run_id,
            "descriptor": descriptor,
            "market": descriptor,
            "snapshot": snapshot,
            "manifest": manifest,
        }
        if report_path.exists():
            payload["report_path"] = str(report_path)
        if isinstance(report_payload, dict):
            payload["report"] = report_payload
            report_surface_context = _report_surface_context(report_payload)
            payload["report_surface_context"] = report_surface_context
            order_trace_audit = _report_order_trace_audit(report_payload)
            if order_trace_audit is not None:
                payload["order_trace_audit"] = order_trace_audit
            advisor_architecture_payload = report_payload.get("advisor_architecture")
            if advisor_architecture_payload is not None:
                payload["advisor_architecture"] = AdvisorArchitectureSurface.model_validate(advisor_architecture_payload)
            payload.update(_replay_postmortem_surfaces(report_payload))
            if "surface_enrichment" in report_payload:
                payload["surface_enrichment"] = report_payload["surface_enrichment"]
        return payload
    forecast = packets["forecast"]
    recommendation = packets["recommendation"]
    decision = packets["decision"]
    advisor_architecture = None
    if isinstance(report_payload, dict):
        report_architecture = report_payload.get("advisor_architecture")
        if report_architecture is not None:
            advisor_architecture = AdvisorArchitectureSurface.model_validate(report_architecture)
    packet_bundle = {
        "schema_version": "v1",
        "packet_version": forecast.packet_version,
        "compatibility_mode": forecast.compatibility_mode.value,
        "forecast": forecast.surface(),
        "recommendation": recommendation.surface(),
        "decision": decision.surface(),
        "advisor_architecture": None if advisor_architecture is None else advisor_architecture.model_dump(mode="json"),
        "surface_enrichment": {
            "next_review_at": utc_isoformat(forecast.next_review_at),
            "resolution_policy_missing": bool(forecast.metadata.get("resolution_policy_missing", False) or not forecast.resolution_policy_ref),
            "requires_manual_review": bool(forecast.metadata.get("requires_manual_review", False)),
        },
    }
    payload: dict[str, Any] = {
        "run_id": run_id,
        "descriptor": descriptor,
        "market": descriptor,
        "snapshot": snapshot,
        "forecast": forecast,
        "recommendation": recommendation,
        "decision": decision,
        "advisor_architecture": advisor_architecture,
        "packet_bundle": packet_bundle,
        "manifest": manifest,
        "surface_enrichment": dict(packet_bundle["surface_enrichment"]),
    }
    if report_path.exists():
        payload["report_path"] = str(report_path)
        if isinstance(report_payload, dict):
            payload["report"] = report_payload
            report_surface_context = _report_surface_context(report_payload)
            payload["report_surface_context"] = report_surface_context
            order_trace_audit = _report_order_trace_audit(report_payload)
            if order_trace_audit is not None:
                payload["order_trace_audit"] = order_trace_audit
            payload.update(_replay_postmortem_surfaces(report_payload))
            if "surface_enrichment" in report_payload:
                payload["surface_enrichment"] = report_payload["surface_enrichment"]
    replay_report_path = paths.replay_report_path(run_id)
    if replay_report_path.exists():
        replay_report = ReplayReport.model_validate(load_json(replay_report_path))
        payload["replay_report"] = replay_report
        payload["replay_postmortem"] = build_replay_postmortem(replay_report)
        payload["replay_report_path"] = str(replay_report_path)
    return payload


def replay_market_postmortem_sync(run_id: str, *, base_dir: str | Path | None = None) -> dict[str, Any]:
    payload = replay_market_run_sync(run_id, base_dir=base_dir)
    replay_postmortem = payload.get("replay_postmortem")
    supplemental_postmortems = {
        key: payload[key]
        for key in ("shadow_postmortem", "slippage_postmortem", "microstructure_postmortem")
        if payload.get(key) is not None
    }
    if replay_postmortem is None:
        return {
            "run_id": run_id,
            "exists": bool(supplemental_postmortems),
            "replay_report_path": payload.get("replay_report_path"),
            "replay_postmortem": None,
            "packet_bundle": payload.get("packet_bundle"),
            "surface_enrichment": payload.get("surface_enrichment"),
            "report_surface_context": payload.get("report_surface_context"),
            "order_trace_audit": payload.get("order_trace_audit"),
            **supplemental_postmortems,
        }
    return {
        "run_id": run_id,
        "exists": True,
        "replay_report_path": payload.get("replay_report_path"),
        "replay_report": payload.get("replay_report"),
        "replay_postmortem": replay_postmortem,
        "packet_bundle": payload.get("packet_bundle"),
        "surface_enrichment": payload.get("surface_enrichment"),
        "report_surface_context": payload.get("report_surface_context"),
        "order_trace_audit": payload.get("order_trace_audit"),
        **supplemental_postmortems,
    }
