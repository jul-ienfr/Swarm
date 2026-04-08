from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence
from uuid import uuid4

from pydantic import BaseModel, Field

from .capital_ledger import CapitalLedgerSnapshot, capital_freeze_reasons
from .models import ExecutionProjectionMode, MarketDescriptor, VenueHealthReport, _coerce_projection_mode


class RuntimeGuardVerdict(str, Enum):
    ok = "ok"
    degraded = "degraded"
    blocked = "blocked"


class RuntimeGuardTrace(BaseModel):
    schema_version: str = "v1"
    trace_id: str = Field(default_factory=lambda: f"rguard_{uuid4().hex[:12]}")
    run_id: str
    market_id: str
    venue: str
    requested_mode: str
    verdict: RuntimeGuardVerdict = RuntimeGuardVerdict.ok
    kill_switch_triggered: bool = False
    capital_frozen: bool = False
    capital_freeze_reasons: list[str] = Field(default_factory=list)
    reconciliation_drift_usd: float | None = None
    reconciliation_reasons: list[str] = Field(default_factory=list)
    venue_health_status: str | None = None
    venue_health_reasons: list[str] = Field(default_factory=list)
    human_approval_required: bool = False
    human_approval_passed: bool = False
    human_approval_reasons: list[str] = Field(default_factory=list)
    manual_review_categories: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    degraded_reasons: list[str] = Field(default_factory=list)
    incident_alerts: list[str] = Field(default_factory=list)
    incident_summary: str = ""
    incident_runbook: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def incident_trace(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class RuntimeGuardMonitorReport(BaseModel):
    schema_version: str = "v1"
    monitor_id: str = Field(default_factory=lambda: f"rguardmon_{uuid4().hex[:12]}")
    run_id: str | None = None
    trace_count: int = 0
    ok_count: int = 0
    degraded_count: int = 0
    blocked_count: int = 0
    latest_verdict: RuntimeGuardVerdict = RuntimeGuardVerdict.ok
    latest_trace: RuntimeGuardTrace | None = None
    recovered: bool = False
    incident_alerts: list[str] = Field(default_factory=list)
    incident_runbook: dict[str, Any] = Field(default_factory=dict)
    shadow_ready: bool = False
    recovery_required: bool = False
    summary: str = ""
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


def monitor_runtime_guard(
    traces: Sequence[RuntimeGuardTrace] | RuntimeGuardTrace,
    *,
    run_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> RuntimeGuardMonitorReport:
    trace_list = [traces] if isinstance(traces, RuntimeGuardTrace) else list(traces)
    if not trace_list:
        return RuntimeGuardMonitorReport(
            run_id=run_id,
            summary="traces=0; status=empty",
            metadata=dict(metadata or {}),
        )

    latest_trace = trace_list[-1]
    prior_unhealthy = any(trace.verdict != RuntimeGuardVerdict.ok for trace in trace_list[:-1])
    blocked_count = sum(1 for trace in trace_list if trace.verdict == RuntimeGuardVerdict.blocked)
    degraded_count = sum(1 for trace in trace_list if trace.verdict == RuntimeGuardVerdict.degraded)
    ok_count = sum(1 for trace in trace_list if trace.verdict == RuntimeGuardVerdict.ok)
    incident_alerts = list(
        dict.fromkeys(alert for trace in trace_list for alert in trace.incident_alerts)
    )
    recovery_required = blocked_count > 0 or degraded_count > 0
    recovered = latest_trace.verdict == RuntimeGuardVerdict.ok and prior_unhealthy
    summary = (
        f"traces={len(trace_list)}; ok={ok_count}; degraded={degraded_count}; blocked={blocked_count}; "
        f"latest={latest_trace.verdict.value}; recovery_required={recovery_required}; recovered={recovered}"
    )
    return RuntimeGuardMonitorReport(
        run_id=run_id or latest_trace.run_id,
        trace_count=len(trace_list),
        ok_count=ok_count,
        degraded_count=degraded_count,
        blocked_count=blocked_count,
        latest_verdict=latest_trace.verdict,
        latest_trace=latest_trace,
        recovered=recovered,
        incident_alerts=incident_alerts,
        incident_runbook=latest_trace.incident_runbook,
        shadow_ready=blocked_count == 0,
        recovery_required=recovery_required,
        summary=summary,
        metadata={
            **dict(metadata or {}),
            "trace_verdicts": [trace.verdict.value for trace in trace_list],
            "latest_runbook_id": latest_trace.incident_runbook.get("runbook_id"),
        },
    )


def build_runtime_guard_trace(
    *,
    run_id: str,
    market: MarketDescriptor,
    requested_mode: Any,
    ledger_before: CapitalLedgerSnapshot,
    request_metadata: Mapping[str, Any] | None = None,
    reconciliation_drift_usd: float | None = None,
    venue_health: VenueHealthReport | None = None,
    kill_switch_triggered: bool = False,
) -> RuntimeGuardTrace:
    metadata = dict(request_metadata or {})
    requested = _coerce_projection_mode(requested_mode)
    blocked_reasons: list[str] = []
    degraded_reasons: list[str] = []

    if kill_switch_triggered:
        blocked_reasons.append("kill_switch_enabled")

    freeze_reasons = capital_freeze_reasons(ledger_before, extra_metadata=metadata)
    capital_frozen = bool(freeze_reasons)
    if capital_frozen:
        blocked_reasons.extend(freeze_reasons)

    reconciliation_reasons: list[str] = []
    drift_value = _resolve_reconciliation_drift(reconciliation_drift_usd, metadata)
    if drift_value is not None:
        reconciliation_reasons.append(f"reconciliation_drift_usd:{drift_value:.6f}")
        threshold = _float_metadata(
            metadata,
            "max_reconciliation_drift_usd",
            default=_float_metadata(ledger_before.metadata, "max_reconciliation_drift_usd", default=0.0),
        )
        if threshold > 0.0 and drift_value > threshold:
            blocked_reasons.append(f"reconciliation_drift_exceeded:{drift_value:.6f}/{threshold:.6f}")
        elif drift_value > 0.0:
            degraded_reasons.append(f"reconciliation_drift:{drift_value:.6f}")

    if metadata.get("reconciliation_manual_review_required") or metadata.get("reconciliation_status") == "drifted":
        blocked_reasons.append("reconciliation_manual_review_required")
        reconciliation_reasons.append("reconciliation_manual_review_required")
    if metadata.get("reconciliation_open_drift"):
        blocked_reasons.append("reconciliation_open_drift")
        reconciliation_reasons.append("reconciliation_open_drift")

    auth_failure = _auth_failure_reason(metadata)
    if auth_failure is not None:
        blocked_reasons.append(auth_failure)

    manipulation_reason, manipulation_should_block = _manipulation_suspicion_state(metadata)
    if manipulation_reason is not None:
        if manipulation_should_block:
            blocked_reasons.append(manipulation_reason)
        else:
            degraded_reasons.append(manipulation_reason)

    if _metadata_bool(metadata, "social_bridge_required") and not _metadata_bool(metadata, "social_bridge_available"):
        degraded_reasons.append("social_bridge_unavailable")

    risk_threshold_blocked_reasons, risk_threshold_degraded_reasons, risk_thresholds = _risk_threshold_state(metadata)
    blocked_reasons.extend(risk_threshold_blocked_reasons)
    degraded_reasons.extend(risk_threshold_degraded_reasons)

    venue_health_status = None
    venue_health_reasons: list[str] = []
    if venue_health is not None:
        venue_health_status = "healthy" if venue_health.healthy else "degraded"
        if not venue_health.healthy:
            if venue_health.details.get("degraded_mode") or "degraded" in venue_health.message.lower():
                degraded_reasons.append(f"venue_degraded:{venue_health.message}")
                venue_health_reasons.append(f"venue_degraded:{venue_health.message}")
            else:
                blocked_reasons.append(f"venue_unhealthy:{venue_health.message}")
                venue_health_reasons.append(f"venue_unhealthy:{venue_health.message}")

    human_approval_required = bool(metadata.get("human_approval_required_before_live", False)) and requested == ExecutionProjectionMode.live
    human_approval_passed = _metadata_bool(metadata, "human_approval_passed")
    human_approval_reasons: list[str] = []
    if human_approval_required:
        if human_approval_passed:
            human_approval_reasons.append("human_approval_recorded")
            approval_actor = _first_non_empty(
                metadata.get("human_approval_actor"),
                metadata.get("approval_actor"),
                metadata.get("approved_by"),
            )
            if approval_actor:
                human_approval_reasons.append(f"human_approval_actor:{approval_actor}")
        else:
            blocked_reasons.append("human_approval_required_before_live")
            human_approval_reasons.append("human_approval_required_before_live")
            approval_actor = _first_non_empty(
                metadata.get("human_approval_actor"),
                metadata.get("approval_actor"),
                metadata.get("approved_by"),
            )
            if approval_actor:
                human_approval_reasons.append(f"human_approval_actor:{approval_actor}")

    if requested == ExecutionProjectionMode.live and metadata.get("live_gate_passed") is False:
        degraded_reasons.append("live_gate_not_passed")

    verdict = RuntimeGuardVerdict.blocked if blocked_reasons else RuntimeGuardVerdict.degraded if degraded_reasons else RuntimeGuardVerdict.ok
    incident_summary = _incident_summary(blocked_reasons=blocked_reasons, degraded_reasons=degraded_reasons)
    incident_runbook = _incident_runbook(
        verdict=verdict,
        blocked_reasons=blocked_reasons,
        degraded_reasons=degraded_reasons,
        human_approval_required=human_approval_required,
        human_approval_passed=human_approval_passed,
        human_approval_reasons=human_approval_reasons,
        manual_review_categories=_manual_review_categories(metadata, blocked_reasons=blocked_reasons, degraded_reasons=degraded_reasons),
        metadata=metadata,
    )
    incident_alerts = _incident_alerts(
        blocked_reasons=blocked_reasons,
        degraded_reasons=degraded_reasons,
        capital_frozen=capital_frozen,
        kill_switch_triggered=kill_switch_triggered,
        human_approval_required=human_approval_required,
        human_approval_passed=human_approval_passed,
        venue_health_reasons=venue_health_reasons,
        reconciliation_reasons=reconciliation_reasons,
    )
    manual_review_categories = _manual_review_categories(metadata, blocked_reasons=blocked_reasons, degraded_reasons=degraded_reasons)
    return RuntimeGuardTrace(
        run_id=run_id,
        market_id=market.market_id,
        venue=market.venue.value,
        requested_mode=requested.value if hasattr(requested, "value") else str(requested),
        verdict=verdict,
        kill_switch_triggered=kill_switch_triggered,
        capital_frozen=capital_frozen,
        capital_freeze_reasons=freeze_reasons,
        reconciliation_drift_usd=drift_value,
        reconciliation_reasons=reconciliation_reasons,
        venue_health_status=venue_health_status,
        venue_health_reasons=venue_health_reasons,
        human_approval_required=human_approval_required,
        human_approval_passed=human_approval_passed,
        human_approval_reasons=human_approval_reasons,
        manual_review_categories=manual_review_categories,
        blocked_reasons=list(dict.fromkeys(blocked_reasons)),
        degraded_reasons=list(dict.fromkeys(degraded_reasons)),
        incident_alerts=incident_alerts,
        incident_summary=incident_summary,
        incident_runbook=incident_runbook,
        metadata={
            **metadata,
            "capital_freeze": capital_frozen,
            "runtime_guard_verdict": verdict.value,
            "incident_alerts": incident_alerts,
            "incident_runbook": incident_runbook,
            "manual_review_categories": manual_review_categories,
            "risk_thresholds": risk_thresholds,
        },
    )


def _resolve_reconciliation_drift(value: float | None, metadata: Mapping[str, Any]) -> float | None:
    if value is not None:
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return None
    for key in ("reconciliation_drift_usd", "open_reconciliation_drift_usd"):
        if key not in metadata:
            continue
        try:
            return max(0.0, float(metadata[key]))
        except (TypeError, ValueError):
            continue
    return None


def _float_metadata(metadata: Mapping[str, Any], key: str, *, default: float = 0.0) -> float:
    value = metadata.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _metadata_bool(metadata: Mapping[str, Any], key: str) -> bool:
    value = metadata.get(key)
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        text = value.strip().lower()
        return text in {"1", "true", "yes", "y", "on", "approved", "recorded"}
    return bool(value)


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = " ".join(str(value).strip().split())
        if text:
            return text
    return None


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _optional_float_metadata(metadata: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key not in metadata:
            continue
        value = metadata.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _optional_int_metadata(metadata: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        if key not in metadata:
            continue
        value = metadata.get(key)
        if value is None:
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return None


def _risk_threshold_state(metadata: Mapping[str, Any]) -> tuple[list[str], list[str], dict[str, Any]]:
    blocked_reasons: list[str] = []
    degraded_reasons: list[str] = []
    risk_thresholds: dict[str, Any] = {}

    snapshot_staleness_ms = _optional_int_metadata(metadata, "snapshot_staleness_ms", "market_snapshot_staleness_ms", "staleness_ms")
    snapshot_ttl_ms = _optional_int_metadata(metadata, "snapshot_ttl_ms", "max_snapshot_staleness_ms")
    snapshot_liquidity_usd = _optional_float_metadata(metadata, "snapshot_liquidity_usd", "liquidity_usd", "market_liquidity_usd")
    snapshot_depth_near_touch = _optional_float_metadata(metadata, "snapshot_depth_near_touch", "depth_near_touch")
    snapshot_edge_after_fees_bps = _optional_float_metadata(
        metadata,
        "snapshot_edge_after_fees_bps",
        "edge_after_fees_bps",
        "trade_intent_edge_after_fees_bps",
        "forecast_edge_after_fees_bps",
    )
    resolution_completeness_score = _optional_float_metadata(
        metadata,
        "resolution_compatibility_score",
        "resolution_guard_policy_completeness_score",
        "policy_completeness_score",
    )
    resolution_coherence_score = _optional_float_metadata(
        metadata,
        "resolution_coherence_score",
        "resolution_guard_policy_coherence_score",
        "policy_coherence_score",
    )
    payout_compatibility_score = _optional_float_metadata(metadata, "payout_compatibility_score")
    currency_compatibility_score = _optional_float_metadata(metadata, "currency_compatibility_score")
    min_liquidity_usd = _optional_float_metadata(metadata, "min_liquidity_usd", "min_liquidity")
    min_depth_near_touch = _optional_float_metadata(metadata, "min_depth_near_touch")
    min_edge_after_fees_bps = _optional_float_metadata(metadata, "min_edge_after_fees_bps", "min_edge_bps")
    min_resolution_compatibility_score = _optional_float_metadata(
        metadata,
        "min_resolution_compatibility_score",
        "min_policy_completeness_score",
        "min_policy_coherence_score",
    )
    min_payout_compatibility_score = _optional_float_metadata(metadata, "min_payout_compatibility_score")
    min_currency_compatibility_score = _optional_float_metadata(metadata, "min_currency_compatibility_score")

    if snapshot_staleness_ms is not None:
        risk_thresholds["snapshot_staleness_ms"] = snapshot_staleness_ms
    if snapshot_ttl_ms is not None:
        risk_thresholds["snapshot_ttl_ms"] = snapshot_ttl_ms
    if snapshot_liquidity_usd is not None:
        risk_thresholds["snapshot_liquidity_usd"] = snapshot_liquidity_usd
    if snapshot_depth_near_touch is not None:
        risk_thresholds["snapshot_depth_near_touch"] = snapshot_depth_near_touch
    if snapshot_edge_after_fees_bps is not None:
        risk_thresholds["snapshot_edge_after_fees_bps"] = snapshot_edge_after_fees_bps
    if resolution_completeness_score is not None:
        risk_thresholds["resolution_compatibility_score"] = resolution_completeness_score
    if resolution_coherence_score is not None:
        risk_thresholds["resolution_coherence_score"] = resolution_coherence_score
    if payout_compatibility_score is not None:
        risk_thresholds["payout_compatibility_score"] = payout_compatibility_score
    if currency_compatibility_score is not None:
        risk_thresholds["currency_compatibility_score"] = currency_compatibility_score
    if min_liquidity_usd is not None:
        risk_thresholds["min_liquidity_usd"] = min_liquidity_usd
    if min_depth_near_touch is not None:
        risk_thresholds["min_depth_near_touch"] = min_depth_near_touch
    if min_edge_after_fees_bps is not None:
        risk_thresholds["min_edge_after_fees_bps"] = min_edge_after_fees_bps
    if min_resolution_compatibility_score is not None:
        risk_thresholds["min_resolution_compatibility_score"] = min_resolution_compatibility_score
    if min_payout_compatibility_score is not None:
        risk_thresholds["min_payout_compatibility_score"] = min_payout_compatibility_score
    if min_currency_compatibility_score is not None:
        risk_thresholds["min_currency_compatibility_score"] = min_currency_compatibility_score

    if snapshot_staleness_ms is not None and snapshot_ttl_ms is not None:
        if snapshot_staleness_ms > snapshot_ttl_ms:
            blocked_reasons.append(f"snapshot_stale:{snapshot_staleness_ms}/{snapshot_ttl_ms}")

    if min_liquidity_usd is not None and snapshot_liquidity_usd is not None:
        if snapshot_liquidity_usd < min_liquidity_usd:
            blocked_reasons.append(f"liquidity_below_minimum:{snapshot_liquidity_usd:.2f}/{min_liquidity_usd:.2f}")

    if min_depth_near_touch is not None and snapshot_depth_near_touch is not None:
        if snapshot_depth_near_touch < min_depth_near_touch:
            blocked_reasons.append(
                f"depth_near_touch_below_minimum:{snapshot_depth_near_touch:.2f}/{min_depth_near_touch:.2f}"
            )

    if min_edge_after_fees_bps is not None and snapshot_edge_after_fees_bps is not None:
        if snapshot_edge_after_fees_bps <= min_edge_after_fees_bps:
            blocked_reasons.append(
                f"edge_after_fees_below_minimum:{snapshot_edge_after_fees_bps:.2f}/{min_edge_after_fees_bps:.2f}"
            )

    if min_resolution_compatibility_score is not None and resolution_completeness_score is not None:
        if resolution_completeness_score < min_resolution_compatibility_score:
            blocked_reasons.append(
                "resolution_compatibility_below_minimum:"
                f"{resolution_completeness_score:.3f}/{min_resolution_compatibility_score:.3f}"
            )

    if min_resolution_compatibility_score is not None and resolution_coherence_score is not None:
        if resolution_coherence_score < min_resolution_compatibility_score:
            blocked_reasons.append(
                "resolution_coherence_below_minimum:"
                f"{resolution_coherence_score:.3f}/{min_resolution_compatibility_score:.3f}"
            )

    if min_payout_compatibility_score is not None and payout_compatibility_score is not None:
        if payout_compatibility_score < min_payout_compatibility_score:
            blocked_reasons.append(
                "payout_compatibility_below_minimum:"
                f"{payout_compatibility_score:.3f}/{min_payout_compatibility_score:.3f}"
            )

    if min_currency_compatibility_score is not None and currency_compatibility_score is not None:
        if currency_compatibility_score < min_currency_compatibility_score:
            blocked_reasons.append(
                "currency_compatibility_below_minimum:"
                f"{currency_compatibility_score:.3f}/{min_currency_compatibility_score:.3f}"
            )

    return _dedupe(blocked_reasons), _dedupe(degraded_reasons), risk_thresholds


def _manual_review_categories(
    metadata: Mapping[str, Any],
    *,
    blocked_reasons: list[str],
    degraded_reasons: list[str],
) -> list[str]:
    categories: list[str] = []
    categories.extend(_normalized_category_list(metadata.get("manual_review_categories")))
    categories.extend(_normalized_category_list(metadata.get("manual_review_category")))
    categories.extend(_normalized_category_list(metadata.get("manual_review_reason_categories")))
    if _metadata_bool(metadata, "capital_transfer_latency_exceeded"):
        categories.append("capital")
    if _metadata_bool(metadata, "resolved_markets_for_live") is False and metadata.get("min_resolved_markets_for_live"):
        categories.append("promotion")
    if _metadata_bool(metadata, "manual_review_category_match"):
        categories.append("manual_review")
    for reason in [*blocked_reasons, *degraded_reasons]:
        lowered = str(reason).strip().lower()
        if not lowered:
            continue
        if "reconciliation" in lowered:
            categories.append("reconciliation")
        if "capital_transfer_latency" in lowered or lowered.startswith("capital_") or "cash_" in lowered:
            categories.append("capital")
        if "liquidity" in lowered or "depth_near_touch" in lowered or "snapshot_stale" in lowered:
            categories.append("data")
        if "edge_after_fees" in lowered or lowered.startswith("edge_"):
            categories.append("edge")
        if "venue_" in lowered:
            categories.append("venue")
        if "human_approval" in lowered:
            categories.append("approval")
        if "manipulation" in lowered:
            categories.append("manipulation")
        if "execution_projection" in lowered or "projection_" in lowered:
            categories.append("promotion")
        if "resolution_guard" in lowered or "resolution_policy" in lowered:
            categories.append("resolution")
        if (
            "resolution_compatibility" in lowered
            or "resolution_coherence" in lowered
            or "resolution_policy_completeness" in lowered
            or "resolution_policy_coherence" in lowered
            or "payout_compatibility" in lowered
            or "currency_compatibility" in lowered
        ):
            categories.append("resolution")
    return list(dict.fromkeys(item for item in categories if item))


def _normalized_category_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    else:
        items = list(value)
    normalized: list[str] = []
    for item in items:
        text = " ".join(str(item).strip().split()).lower()
        if text:
            normalized.append(text)
    return normalized


def _incident_runbook(
    *,
    verdict: RuntimeGuardVerdict,
    blocked_reasons: list[str],
    degraded_reasons: list[str],
    human_approval_required: bool,
    human_approval_passed: bool,
    human_approval_reasons: list[str],
    manual_review_categories: list[str],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    auth_failure = _auth_failure_reason(metadata)
    if _metadata_bool(metadata, "social_bridge_required") and not _metadata_bool(metadata, "social_bridge_available"):
        return {
            "runbook_id": "social_bridge_unavailable",
            "runbook_kind": "degraded_mode",
            "summary": "The social bridge is unavailable, so the run should continue in market-only mode.",
            "recommended_action": "continue_market_only",
            "owner": "operator",
            "priority": "medium",
            "status": "degraded",
            "trigger_reasons": list(dict.fromkeys([*blocked_reasons, *degraded_reasons, "social_bridge_unavailable"])),
            "next_steps": [
                "Continue the run in market-only mode.",
                "Record the missing bridge context in the run artifacts.",
                "Rehydrate the bridge context if social evidence becomes available later.",
            ],
            "signals": {
                "social_bridge_available": False,
                "social_bridge_required": True,
                "social_bridge_status": metadata.get("social_bridge_status", "unavailable"),
                "manual_review_categories": manual_review_categories,
            },
        }
    auth_failure = _auth_failure_reason(metadata)
    if auth_failure is not None:
        return {
            "runbook_id": "compliance_auth_failure",
            "runbook_kind": "approval_gate",
            "summary": "Execution is blocked because authorization or compliance approval failed.",
            "recommended_action": "stay_dry_run",
            "owner": "human_operator",
            "priority": "critical",
            "status": "blocked",
            "trigger_reasons": list(dict.fromkeys([*blocked_reasons, auth_failure])),
            "next_steps": [
                "Review authorization and compliance approval state.",
                "Record the missing approval or authorization before retrying live.",
                "Keep the run in paper or shadow mode until the gate is satisfied.",
            ],
            "signals": {
                "auth_authorized": _metadata_bool(metadata, "auth_authorized") or _metadata_bool(metadata, "authorized"),
                "auth_compliance_approved": _metadata_bool(metadata, "auth_compliance_approved") or _metadata_bool(metadata, "compliance_approved"),
                "auth_principal": metadata.get("auth_principal") or metadata.get("principal"),
                "auth_scopes": list(metadata.get("auth_scopes") or metadata.get("scopes") or []),
                "auth_failure_reason": auth_failure,
                "manual_review_categories": manual_review_categories,
            },
        }
    manipulation_runbook = _manipulation_runbook(metadata, verdict=verdict, blocked_reasons=blocked_reasons, degraded_reasons=degraded_reasons)
    if manipulation_runbook is not None:
        return manipulation_runbook
    if human_approval_required and not human_approval_passed:
        return {
            "runbook_id": "human_approval_required_before_live",
            "runbook_kind": "approval_gate",
            "summary": "Live execution is blocked until a human approval is recorded.",
            "recommended_action": "stay_dry_run",
            "owner": "human_operator",
            "priority": "high",
            "status": "blocked",
            "trigger_reasons": list(dict.fromkeys([*blocked_reasons, *human_approval_reasons])),
            "next_steps": [
                "Review the execution projection and runtime guard summary.",
                "Record explicit human approval in request metadata before retrying live.",
                "If approval cannot be recorded, continue in paper or shadow mode.",
            ],
            "signals": {
                "human_approval_required": human_approval_required,
                "human_approval_passed": human_approval_passed,
                "requested_mode": metadata.get("requested_mode"),
                "requested_run_mode": metadata.get("requested_run_mode"),
                "manual_review_categories": manual_review_categories,
            },
        }
    if verdict == RuntimeGuardVerdict.blocked:
        return {
            "runbook_id": "runtime_guard_blocked",
            "runbook_kind": "incident",
            "summary": "Runtime guard blocked the execution path.",
            "recommended_action": "review_blocked_reasons",
            "owner": "operator",
            "priority": "high",
            "status": "blocked",
            "trigger_reasons": list(dict.fromkeys(blocked_reasons)),
            "next_steps": [
                "Inspect the blocked reasons and remove the underlying guard condition.",
                "Confirm the venue, capital, reconciliation and venue-health state.",
                "Retry only after the underlying blocker is cleared.",
            ],
            "signals": {
                "blocked_reasons": list(blocked_reasons[:5]),
                "degraded_reasons": list(degraded_reasons[:5]),
                "manual_review_categories": manual_review_categories,
            },
        }
    if verdict == RuntimeGuardVerdict.degraded:
        return {
            "runbook_id": "runtime_guard_degraded",
            "runbook_kind": "degraded_mode",
            "summary": "Runtime guard degraded the execution path.",
            "recommended_action": "downgrade_or_review",
            "owner": "operator",
            "priority": "medium",
            "status": "degraded",
            "trigger_reasons": list(dict.fromkeys(degraded_reasons)),
            "next_steps": [
                "Review degraded signals and decide whether paper or shadow mode is acceptable.",
                "Inspect venue-health and reconciliation drift if present.",
            ],
            "signals": {
                "blocked_reasons": list(blocked_reasons[:5]),
                "degraded_reasons": list(degraded_reasons[:5]),
                "manual_review_categories": manual_review_categories,
            },
        }
    return {
        "runbook_id": "runtime_guard_ok",
        "runbook_kind": "ok",
        "summary": "Runtime guard reported no blocking or degrading conditions.",
        "recommended_action": "proceed",
        "owner": "system",
        "priority": "low",
        "status": "ok",
        "trigger_reasons": [],
        "next_steps": [
            "Proceed with the projected execution mode.",
        ],
            "signals": {
                "blocked_reasons": [],
                "degraded_reasons": [],
                "manual_review_categories": manual_review_categories,
            },
        }


def _auth_failure_reason(metadata: Mapping[str, Any]) -> str | None:
    auth_keys_present = any(key in metadata for key in ("auth_authorized", "authorized", "auth_compliance_approved", "compliance_approved"))
    if not auth_keys_present:
        return None
    if _metadata_bool(metadata, "auth_authorized") or _metadata_bool(metadata, "authorized"):
        if _metadata_bool(metadata, "auth_compliance_approved") or _metadata_bool(metadata, "compliance_approved"):
            return None
    return "compliance_auth_failure"


def _manipulation_suspicion_state(metadata: Mapping[str, Any]) -> tuple[str | None, bool]:
    signal_only = _metadata_bool(metadata, "manipulation_guard_signal_only") or _metadata_bool(metadata, "manipulation_suspicion")
    severity = _first_non_empty(metadata.get("manipulation_guard_severity"), metadata.get("manipulation_severity")) or "low"
    if not signal_only and severity not in {"medium", "high", "critical"}:
        return None, False
    should_block = severity in {"high", "critical"} or signal_only
    return "manipulation_suspicion", should_block


def _manipulation_runbook(
    metadata: Mapping[str, Any],
    *,
    verdict: RuntimeGuardVerdict,
    blocked_reasons: list[str],
    degraded_reasons: list[str],
) -> dict[str, Any] | None:
    signal_only = _metadata_bool(metadata, "manipulation_guard_signal_only") or _metadata_bool(metadata, "manipulation_suspicion")
    severity = _first_non_empty(metadata.get("manipulation_guard_severity"), metadata.get("manipulation_severity")) or "low"
    if not signal_only and severity not in {"medium", "high", "critical"}:
        return None

    should_block = verdict == RuntimeGuardVerdict.blocked or severity in {"high", "critical"} or signal_only
    status = "blocked" if should_block else "degraded"
    runbook_kind = "incident" if should_block else "degraded_mode"
    recommended_action = "stay_dry_run" if should_block else "continue_market_only"
    summary = (
        "Manipulation suspicion is high enough to block execution."
        if should_block
        else "Manipulation suspicion is present, so the run should stay signal-only."
    )
    return {
        "runbook_id": "manipulation_suspicion",
        "runbook_kind": runbook_kind,
        "summary": summary,
        "recommended_action": recommended_action,
        "owner": "operator",
        "priority": "high" if should_block else "medium",
        "status": status,
        "trigger_reasons": list(
            dict.fromkeys(
                [
                    *blocked_reasons,
                    *degraded_reasons,
                    "manipulation_guard_signal_only" if signal_only else "manipulation_suspicion",
                ]
            )
        ),
        "next_steps": [
            "Reclassify the evidence as signal-only.",
            "Raise corroboration and liquidity thresholds before retrying.",
            "Review the comment / evidence provenance before any live action.",
        ],
        "signals": {
            "manipulation_guard_signal_only": signal_only,
            "manipulation_guard_severity": severity,
        },
    }


def _incident_summary(*, blocked_reasons: list[str], degraded_reasons: list[str]) -> str:
    if not blocked_reasons and not degraded_reasons:
        return "runtime_guard_ok"
    parts = []
    if blocked_reasons:
        parts.append(f"blocked={';'.join(blocked_reasons[:3])}")
    if degraded_reasons:
        parts.append(f"degraded={';'.join(degraded_reasons[:3])}")
    return " | ".join(parts)


def _incident_alerts(
    *,
    blocked_reasons: list[str],
    degraded_reasons: list[str],
    capital_frozen: bool,
    kill_switch_triggered: bool,
    human_approval_required: bool,
    human_approval_passed: bool,
    venue_health_reasons: list[str],
    reconciliation_reasons: list[str],
) -> list[str]:
    alerts: list[str] = []
    reasons = [*blocked_reasons, *degraded_reasons, *venue_health_reasons, *reconciliation_reasons]
    if kill_switch_triggered or any("kill_switch" in reason for reason in reasons):
        alerts.append("kill_switch")
    if capital_frozen:
        alerts.append("capital_frozen")
    if any("stale" in reason for reason in reasons):
        alerts.append("stale_data")
    if any("liquidity" in reason or "depth_near_touch" in reason for reason in reasons):
        alerts.append("market_data_quality")
    if any("edge_after_fees" in reason for reason in reasons):
        alerts.append("edge_quality")
    if any("reconciliation" in reason for reason in reasons):
        alerts.append("reconciliation_drift")
    if any(
        "resolution_compatibility" in reason
        or "resolution_coherence" in reason
        or "resolution_policy" in reason
        or "payout_compatibility" in reason
        or "currency_compatibility" in reason
        for reason in reasons
    ):
        alerts.append("resolution_quality")
    if venue_health_reasons:
        alerts.append("venue_health")
    if any("compliance_auth_failure" in reason for reason in reasons):
        alerts.append("compliance_auth_failure")
    if any("manipulation_suspicion" in reason for reason in reasons):
        alerts.append("manipulation_suspicion")
    if "social_bridge_unavailable" in reasons:
        alerts.append("social_bridge_unavailable")
    if human_approval_required and not human_approval_passed:
        alerts.append("human_approval_required")
    return list(dict.fromkeys(alerts))
