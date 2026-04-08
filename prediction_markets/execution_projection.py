from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import (
    CapitalLedgerSnapshot,
    ExecutionComplianceSnapshot,
    ExecutionComplianceStatus,
    ExecutionProjection,
    ExecutionProjectionBasis,
    ExecutionProjectionMode,
    ExecutionProjectionModeReport,
    ExecutionProjectionOutcome,
    ExecutionProjectionVerdict,
    ExecutionReadiness,
    MarketDescriptor,
    VenueHealthReport,
    _coerce_projection_mode,
    _utc_now,
    _utc_datetime,
    _projection_summary_text,
    _stable_content_hash,
    min_projection_mode,
)
from .runtime_guard import RuntimeGuardTrace, RuntimeGuardVerdict


@dataclass(slots=True)
class ShadowExecutionProjectionGate:
    projection_id: str
    run_id: str
    market_id: str
    venue: str
    projection_verdict: ExecutionProjectionVerdict
    projected_mode: ExecutionProjectionOutcome
    valid: bool
    expired: bool
    stale: bool
    manual_review_required: bool
    blocked_reasons: list[str]
    degraded_reasons: list[str]
    incident_alerts: list[str]
    incident_summary: str
    incident_runbook: dict[str, Any]
    metadata: dict[str, Any]


def build_shadow_execution_projection_gate(
    projection: ExecutionProjection,
    *,
    as_of: datetime | None = None,
    runtime_guard: RuntimeGuardTrace | None = None,
) -> ShadowExecutionProjectionGate:
    check_at = as_of or datetime.now(timezone.utc)
    blocked_reasons: list[str] = []
    degraded_reasons: list[str] = []
    incident_alerts: list[str] = []

    expired = projection.is_expired(check_at)
    stale = projection.is_stale(check_at)
    if expired:
        blocked_reasons.append("execution_projection_expired")
        incident_alerts.append("stale_data")
    if stale:
        blocked_reasons.append("execution_projection_stale")
        incident_alerts.append("stale_data")
    if projection.projection_verdict == ExecutionProjectionVerdict.blocked:
        blocked_reasons.append("execution_projection_blocked")
        incident_alerts.append("projection_blocked")
    if projection.projected_mode == ExecutionProjectionOutcome.blocked:
        blocked_reasons.append("execution_projection_no_effective_mode")
    if projection.manual_review_required:
        blocked_reasons.append("execution_projection_manual_review_required")
        incident_alerts.append("manual_review")

    if runtime_guard is not None:
        incident_alerts.extend(runtime_guard.incident_alerts)
        if runtime_guard.verdict == RuntimeGuardVerdict.blocked:
            blocked_reasons.extend([f"runtime_guard:{reason}" for reason in runtime_guard.blocked_reasons])
        elif runtime_guard.verdict == RuntimeGuardVerdict.degraded:
            degraded_reasons.extend([f"runtime_guard:{reason}" for reason in runtime_guard.degraded_reasons])
        if runtime_guard.kill_switch_triggered:
            blocked_reasons.append("runtime_guard_kill_switch")
            incident_alerts.append("kill_switch")
        if runtime_guard.capital_frozen:
            degraded_reasons.append("runtime_guard_capital_frozen")
        if any("stale" in reason for reason in runtime_guard.blocked_reasons + runtime_guard.degraded_reasons):
            incident_alerts.append("stale_data")
        if any("reconciliation" in reason for reason in runtime_guard.blocked_reasons + runtime_guard.degraded_reasons):
            incident_alerts.append("reconciliation_drift")
        if any("human_approval" in reason for reason in runtime_guard.blocked_reasons + runtime_guard.degraded_reasons):
            incident_alerts.append("human_approval_required")

    incident_alerts = list(dict.fromkeys(incident_alerts))
    valid = not blocked_reasons and projection.projection_verdict != ExecutionProjectionVerdict.blocked and not expired and not stale
    incident_summary = _shadow_projection_summary(
        projection=projection,
        blocked_reasons=blocked_reasons,
        degraded_reasons=degraded_reasons,
        valid=valid,
    )
    incident_runbook = _shadow_projection_runbook(
        projection=projection,
        blocked_reasons=blocked_reasons,
        degraded_reasons=degraded_reasons,
        incident_alerts=incident_alerts,
        runtime_guard=runtime_guard,
    )
    return ShadowExecutionProjectionGate(
        projection_id=projection.projection_id,
        run_id=projection.run_id,
        market_id=projection.market_id,
        venue=projection.venue.value,
        projection_verdict=projection.projection_verdict,
        projected_mode=projection.projected_mode,
        valid=valid,
        expired=expired,
        stale=stale,
        manual_review_required=projection.manual_review_required,
        blocked_reasons=list(dict.fromkeys(blocked_reasons)),
        degraded_reasons=list(dict.fromkeys(degraded_reasons)),
        incident_alerts=incident_alerts,
        incident_summary=incident_summary,
        incident_runbook=incident_runbook,
        metadata={
            "highest_safe_mode": None if projection.highest_safe_mode is None else projection.highest_safe_mode.value,
            "highest_authorized_mode": projection.highest_authorized_mode.value,
            "requested_mode": projection.requested_mode.value,
            "projected_mode": projection.projected_mode.value,
            "projection_verdict": projection.projection_verdict.value,
            "projection_expired": expired,
            "projection_stale": stale,
            "runtime_guard_verdict": None if runtime_guard is None else runtime_guard.verdict.value,
            "runtime_guard_trace_id": None if runtime_guard is None else runtime_guard.trace_id,
        },
    )


def _shadow_projection_summary(
    *,
    projection: ExecutionProjection,
    blocked_reasons: list[str],
    degraded_reasons: list[str],
    valid: bool,
) -> str:
    if valid:
        return (
            f"shadow gate ready: requested {projection.requested_mode.value} -> projected {projection.projected_mode.value}"
        )
    parts = [f"projection={projection.projection_id}", f"projected_mode={projection.projected_mode.value}"]
    if blocked_reasons:
        parts.append(f"blocked={';'.join(blocked_reasons[:3])}")
    if degraded_reasons:
        parts.append(f"degraded={';'.join(degraded_reasons[:3])}")
    return " | ".join(parts)


def _shadow_projection_runbook(
    *,
    projection: ExecutionProjection,
    blocked_reasons: list[str],
    degraded_reasons: list[str],
    incident_alerts: list[str],
    runtime_guard: RuntimeGuardTrace | None,
) -> dict[str, Any]:
    if runtime_guard is not None and runtime_guard.incident_runbook and runtime_guard.verdict != RuntimeGuardVerdict.ok:
        return {
            **dict(runtime_guard.incident_runbook),
            "incident_alerts": list(incident_alerts),
            "projection_id": projection.projection_id,
            "projection_verdict": projection.projection_verdict.value,
        }
    if blocked_reasons:
        if "execution_projection_missing" in blocked_reasons:
            return {
                "runbook_id": "shadow_execution_projection_missing",
                "runbook_kind": "incident",
                "summary": "Shadow execution requires a persisted ExecutionProjection for the run.",
                "recommended_action": "recompute_projection",
                "owner": "operator",
                "priority": "high",
                "status": "blocked",
                "trigger_reasons": list(blocked_reasons),
                "next_steps": [
                    "Rebuild the execution projection for this run.",
                    "Persist the projection before retrying shadow execution.",
                ],
                "signals": {
                    "alerts": list(incident_alerts),
                    "blocked_reasons": list(blocked_reasons[:5]),
                    "degraded_reasons": list(degraded_reasons[:5]),
                },
            }
        if "execution_projection_stale" in blocked_reasons or "execution_projection_expired" in blocked_reasons:
            return {
                "runbook_id": "shadow_execution_projection_stale",
                "runbook_kind": "incident",
                "summary": "Shadow execution is blocked by a stale or expired execution projection.",
                "recommended_action": "refresh_projection",
                "owner": "operator",
                "priority": "high",
                "status": "blocked",
                "trigger_reasons": list(blocked_reasons),
                "next_steps": [
                    "Recompute the execution projection from the latest market snapshot.",
                    "Inspect data freshness, kill-switch state and reconciliation drift.",
                    "Retry shadow only after the projection is current and valid.",
                ],
                "signals": {
                    "alerts": list(incident_alerts),
                    "blocked_reasons": list(blocked_reasons[:5]),
                    "degraded_reasons": list(degraded_reasons[:5]),
                },
            }
        if "execution_projection_manual_review_required" in blocked_reasons:
            return {
                "runbook_id": "shadow_execution_projection_manual_review",
                "runbook_kind": "approval_gate",
                "summary": "Shadow execution requires manual review before it can materialize paper trades.",
                "recommended_action": "stay_dry_run",
                "owner": "human_operator",
                "priority": "high",
                "status": "blocked",
                "trigger_reasons": list(blocked_reasons),
                "next_steps": [
                    "Review the projection and confirm the intended execution mode.",
                    "Record a human approval if the projection is still acceptable.",
                    "Otherwise keep the run in dry-run or paper-only mode.",
                ],
                "signals": {
                    "alerts": list(incident_alerts),
                    "blocked_reasons": list(blocked_reasons[:5]),
                    "degraded_reasons": list(degraded_reasons[:5]),
                },
            }
        if "runtime_guard_kill_switch" in blocked_reasons:
            return {
                "runbook_id": "shadow_execution_kill_switch",
                "runbook_kind": "incident",
                "summary": "Shadow execution is blocked because the kill switch was triggered.",
                "recommended_action": "stay_dry_run",
                "owner": "operator",
                "priority": "critical",
                "status": "blocked",
                "trigger_reasons": list(blocked_reasons),
                "next_steps": [
                    "Inspect the kill-switch source of truth.",
                    "Leave the run in dry-run until the kill switch is cleared.",
                    "Verify venue and capital state before resuming shadow execution.",
                ],
                "signals": {
                    "alerts": list(incident_alerts),
                    "blocked_reasons": list(blocked_reasons[:5]),
                    "degraded_reasons": list(degraded_reasons[:5]),
                },
            }
    return {
        "runbook_id": "shadow_execution_ok",
        "runbook_kind": "ok",
        "summary": "Shadow execution gate accepted the current execution projection.",
        "recommended_action": "proceed",
        "owner": "system",
        "priority": "low",
        "status": "ok",
        "trigger_reasons": [],
        "next_steps": ["Proceed with shadow execution."],
        "signals": {
            "alerts": list(incident_alerts),
            "blocked_reasons": list(blocked_reasons[:5]),
            "degraded_reasons": list(degraded_reasons[:5]),
        },
    }


def _float_metadata(metadata: dict[str, Any] | None, key: str, *, default: float = 0.0) -> float:
    if metadata is None:
        return default
    value = metadata.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_execution_compliance_snapshot(
    *,
    run_id: str,
    market: MarketDescriptor,
    requested_mode: ExecutionProjectionMode,
    readiness: ExecutionReadiness | None,
    venue_health: VenueHealthReport | None = None,
    capital_snapshot: CapitalLedgerSnapshot | None = None,
    reconciliation: ReconciliationReport | None = None,
    authorized: bool | None = None,
    compliance_approved: bool | None = None,
    jurisdiction_allowed: bool | None = None,
    account_type_allowed: bool | None = None,
    automation_allowed: bool | None = None,
    rate_limit_ok: bool | None = None,
    tos_accepted: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> ExecutionComplianceSnapshot:
    readiness_ok = bool(readiness.can_materialize_trade_intent) if readiness is not None else False
    manual_review_required = bool(readiness.manual_review_required if readiness is not None else False)
    venue_healthy = True if venue_health is None else bool(venue_health.healthy)

    jurisdiction_allowed = True if jurisdiction_allowed is None else bool(jurisdiction_allowed)
    account_type_allowed = True if account_type_allowed is None else bool(account_type_allowed)
    automation_allowed = True if automation_allowed is None else bool(automation_allowed)
    rate_limit_ok = True if rate_limit_ok is None else bool(rate_limit_ok)
    tos_accepted = False if tos_accepted is None else bool(tos_accepted)
    authorized = readiness_ok if authorized is None else bool(authorized)
    compliance_approved = authorized if compliance_approved is None else bool(compliance_approved)

    allowed = (
        readiness_ok
        and jurisdiction_allowed
        and account_type_allowed
        and automation_allowed
        and rate_limit_ok
        and (tos_accepted or requested_mode != ExecutionProjectionMode.live)
        and (venue_healthy or requested_mode == ExecutionProjectionMode.paper)
    )
    if not allowed:
        status = ExecutionComplianceStatus.blocked
    elif manual_review_required or (venue_health is not None and not venue_health.healthy):
        status = ExecutionComplianceStatus.degraded
    else:
        status = ExecutionComplianceStatus.authorized

    if not allowed:
        highest_authorized_mode = ExecutionProjectionOutcome.blocked
    elif compliance_approved and authorized and requested_mode == ExecutionProjectionMode.live and venue_healthy:
        highest_authorized_mode = ExecutionProjectionOutcome.live
    elif readiness is not None and readiness.can_materialize_trade_intent and venue_healthy:
        highest_authorized_mode = ExecutionProjectionOutcome.shadow
    elif readiness is not None and readiness.can_materialize_trade_intent:
        highest_authorized_mode = ExecutionProjectionOutcome.paper
    else:
        highest_authorized_mode = ExecutionProjectionOutcome.blocked

    reasons: list[str] = []
    warnings: list[str] = []
    if not jurisdiction_allowed:
        reasons.append("jurisdiction_not_allowed")
    if not account_type_allowed:
        reasons.append("account_type_not_allowed")
    if not automation_allowed:
        reasons.append("automation_not_allowed")
    if not rate_limit_ok:
        reasons.append("rate_limit_not_ok")
    if not tos_accepted and requested_mode == ExecutionProjectionMode.live:
        reasons.append("tos_not_accepted")
    if not readiness_ok:
        reasons.append("readiness_not_materializable")
    if manual_review_required:
        warnings.append("manual_review_required")
    if venue_health is not None and not venue_health.healthy:
        warnings.append(f"venue_health:{venue_health.message}")
    if capital_snapshot is not None and capital_snapshot.equity <= 0.0:
        warnings.append("capital_equity_non_positive")
    if reconciliation is not None and reconciliation.manual_review_required:
        warnings.append("reconciliation_manual_review_required")

    highest_safe_mode = _highest_safe_mode(
        readiness=readiness,
        venue_health=venue_health,
        capital_snapshot=capital_snapshot,
        reconciliation=reconciliation,
    )

    return ExecutionComplianceSnapshot(
        run_id=run_id,
        market_id=market.market_id,
        venue=market.venue,
        requested_mode=requested_mode,
        highest_authorized_mode=highest_authorized_mode,
        status=status,
        allowed=allowed,
        manual_review_required=manual_review_required,
        jurisdiction_allowed=jurisdiction_allowed,
        account_type_allowed=account_type_allowed,
        automation_allowed=automation_allowed,
        rate_limit_ok=rate_limit_ok,
        tos_accepted=tos_accepted,
        summary=_compliance_summary_text(
            requested_mode=requested_mode,
            allowed=allowed,
            highest_authorized_mode=highest_authorized_mode,
            reasons=reasons,
            warnings=warnings,
        ),
        reasons=reasons,
        warnings=warnings,
        metadata={**dict(metadata or {}), "highest_safe_mode": highest_safe_mode.value, "readiness_ok": readiness_ok},
    )


@dataclass(slots=True)
class ExecutionProjectionRuntime:
    ttl_seconds: float = 300.0
    stale_after_seconds: float = 600.0

    def project(
        self,
        *,
        run_id: str,
        market: MarketDescriptor,
        requested_mode: ExecutionProjectionMode | ExecutionProjectionOutcome | str,
        readiness: ExecutionReadiness | None,
        compliance: ExecutionComplianceSnapshot | None = None,
        capital_snapshot: CapitalLedgerSnapshot | None = None,
        reconciliation: ReconciliationReport | None = None,
        venue_health: VenueHealthReport | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionProjection:
        requested = _coerce_projection_mode(requested_mode)
        capital_available = None
        if capital_snapshot is not None:
            capital_is_frozen = bool(
                capital_snapshot.metadata.get("capital_frozen")
                or capital_snapshot.metadata.get("reconciliation_open_drift")
                or capital_snapshot.metadata.get("reconciliation_manual_review_required")
            )
            capital_available = 0.0 if capital_is_frozen else _float_metadata(
                capital_snapshot.metadata,
                "capital_available_for_execution_usd",
                default=max(0.0, float(capital_snapshot.cash - capital_snapshot.reserved_cash)),
            )
        compliance = compliance or build_execution_compliance_snapshot(
            run_id=run_id,
            market=market,
            requested_mode=requested,
            readiness=readiness,
            venue_health=venue_health,
            capital_snapshot=capital_snapshot,
            reconciliation=reconciliation,
            metadata=metadata,
        )

        readiness_ceiling = self._readiness_ceiling(readiness)
        authorized_ceiling = min_projection_mode(readiness_ceiling, compliance.highest_authorized_mode)
        safety_ceiling, safety_reasons = self._safety_ceiling(
            readiness=readiness,
            capital_snapshot=capital_snapshot,
            capital_available=capital_available,
            reconciliation=reconciliation,
            venue_health=venue_health,
        )

        blocking_reasons = [reason for reason in safety_reasons if reason.startswith("block:")]
        downgrade_reasons = [reason for reason in safety_reasons if not reason.startswith("block:")]
        if compliance.status == ExecutionComplianceStatus.blocked:
            blocking_reasons.extend(compliance.reasons)
        else:
            downgrade_reasons.extend(compliance.reasons)
            downgrade_reasons.extend(compliance.warnings)

        projected_mode = min_projection_mode(requested, authorized_ceiling, safety_ceiling)
        if projected_mode == ExecutionProjectionOutcome.blocked:
            projection_verdict = ExecutionProjectionVerdict.blocked
        elif projected_mode == requested and not downgrade_reasons:
            projection_verdict = ExecutionProjectionVerdict.ready
        else:
            projection_verdict = ExecutionProjectionVerdict.degraded

        highest_safe_mode = None if safety_ceiling == ExecutionProjectionOutcome.blocked else ExecutionProjectionMode(safety_ceiling.value)
        anchor_at = self._anchor_at(
            readiness=readiness,
            compliance=compliance,
            capital_snapshot=capital_snapshot,
            reconciliation=reconciliation,
            venue_health=venue_health,
        )
        expires_at = self._expires_at(anchor_at)
        mode_reports = self._build_mode_reports(
            requested=requested,
            authorized_ceiling=authorized_ceiling,
            safety_ceiling=safety_ceiling,
            readiness=readiness,
            compliance=compliance,
            capital_snapshot=capital_snapshot,
            reconciliation=reconciliation,
            venue_health=venue_health,
        )

        projection_payload = {
            "run_id": run_id,
            "market_id": market.market_id,
            "venue": market.venue.value,
            "requested_mode": requested.value,
            "projected_mode": projected_mode.value,
            "readiness": None if readiness is None else readiness.model_dump(mode="json"),
            "compliance": compliance.model_dump(mode="json"),
            "capital_snapshot": None if capital_snapshot is None else capital_snapshot.model_dump(mode="json"),
            "reconciliation": None if reconciliation is None else reconciliation.model_dump(mode="json"),
            "venue_health": None if venue_health is None else venue_health.model_dump(mode="json"),
            "modes": {mode.value: report.model_dump(mode="json") for mode, report in mode_reports.items()},
            "expires_at": expires_at.isoformat(),
            "metadata": dict(metadata or {}),
        }
        projection_id = f"proj_{_stable_content_hash(projection_payload)[:12]}"

        projection = ExecutionProjection(
            projection_id=projection_id,
            run_id=run_id,
            venue=market.venue,
            market_id=market.market_id,
            requested_mode=requested,
            projected_mode=projected_mode,
            projection_verdict=projection_verdict,
            highest_safe_mode=highest_safe_mode,
            highest_safe_requested_mode=highest_safe_mode,
            highest_authorized_mode=compliance.highest_authorized_mode,
            recommended_effective_mode=projected_mode if projected_mode != ExecutionProjectionOutcome.blocked else None,
            blocking_reasons=self._dedupe(blocking_reasons),
            downgrade_reasons=self._dedupe(downgrade_reasons),
            manual_review_required=bool(
                (readiness.manual_review_required if readiness is not None else False)
                or compliance.manual_review_required
                or (reconciliation.manual_review_required if reconciliation is not None else False)
                or (venue_health is not None and not venue_health.healthy)
            ),
            readiness_ref=readiness.readiness_id if readiness is not None else None,
            compliance_ref=compliance.compliance_id,
            capital_ref=capital_snapshot.snapshot_id if capital_snapshot is not None else None,
            reconciliation_ref=reconciliation.reconciliation_id if reconciliation is not None else None,
            health_ref=None if venue_health is None else f"{venue_health.venue.value}:{venue_health.checked_at.isoformat()}",
            expires_at=expires_at,
            summary=_projection_summary_text(
                requested=requested,
                projected=projected_mode,
                verdict=projection_verdict,
                blocking_reasons=self._dedupe(blocking_reasons),
                downgrade_reasons=self._dedupe(downgrade_reasons),
            ),
            basis=ExecutionProjectionBasis(
                readiness_status="available" if readiness is not None else "unavailable",
                uses_execution_readiness=readiness is not None,
                uses_compliance=True,
                uses_capital=capital_snapshot is not None,
                uses_reconciliation=reconciliation is not None,
                uses_venue_health=venue_health is not None,
                capital_status="available" if capital_available is not None and capital_available > 0.0 else "unavailable",
                reconciliation_status="available" if reconciliation is not None else "unavailable",
                venue_health_status="available" if venue_health is not None else "unavailable",
                compliance_status="available" if compliance is not None else "unavailable",
            ),
            modes=mode_reports,
            metadata={
                **dict(metadata or {}),
                "anchor_at": anchor_at.isoformat(),
                "stale_after_seconds": self.stale_after_seconds,
                "requested_mode": requested.value,
                "projected_mode": projected_mode.value,
                "highest_safe_mode": None if highest_safe_mode is None else highest_safe_mode.value,
                "highest_authorized_mode": compliance.highest_authorized_mode.value,
                "authorized_ceiling": authorized_ceiling.value,
                "safety_ceiling": safety_ceiling.value,
                "capital_available": capital_available,
                "reconciliation_status": None if reconciliation is None else reconciliation.status.value,
                "venue_health_healthy": None if venue_health is None else venue_health.healthy,
            },
            content_hash="",
        )
        projection.content_hash = _stable_content_hash(
            {
                "projection": projection.model_dump(mode="json", exclude={"content_hash"}),
                "readiness": None if readiness is None else readiness.model_dump(mode="json"),
                "compliance": compliance.model_dump(mode="json"),
                "capital_snapshot": None if capital_snapshot is None else capital_snapshot.model_dump(mode="json"),
                "reconciliation": None if reconciliation is None else reconciliation.model_dump(mode="json"),
                "venue_health": None if venue_health is None else venue_health.model_dump(mode="json"),
            }
        )
        return projection

    def _readiness_ceiling(self, readiness: ExecutionReadiness | None) -> ExecutionProjectionOutcome:
        if readiness is None or not readiness.can_materialize_trade_intent:
            return ExecutionProjectionOutcome.blocked
        if readiness.ready_to_live:
            return ExecutionProjectionOutcome.live
        if readiness.route == "shadow":
            return ExecutionProjectionOutcome.shadow
        return ExecutionProjectionOutcome.paper

    def _safety_ceiling(
        self,
        *,
        readiness: ExecutionReadiness | None,
        capital_snapshot: CapitalLedgerSnapshot | None,
        capital_available: float | None,
        reconciliation: ReconciliationReport | None,
        venue_health: VenueHealthReport | None,
    ) -> tuple[ExecutionProjectionOutcome, list[str]]:
        reasons: list[str] = []
        if readiness is None or not readiness.can_materialize_trade_intent:
            return ExecutionProjectionOutcome.blocked, ["block:readiness_not_materializable"]

        ceiling = ExecutionProjectionOutcome.live
        if capital_snapshot is None:
            ceiling = min_projection_mode(ceiling, ExecutionProjectionOutcome.paper)
            reasons.append("warn:capital_missing")
        else:
            available_cash = capital_available if capital_available is not None else max(0.0, float(capital_snapshot.cash - capital_snapshot.reserved_cash))
            projected_size = max(0.0, float(readiness.size_usd))
            if available_cash <= 0.0:
                return ExecutionProjectionOutcome.blocked, ["block:capital_unavailable"]
            if projected_size > 0.0 and available_cash + 1e-9 < projected_size:
                ceiling = min_projection_mode(ceiling, ExecutionProjectionOutcome.paper)
                reasons.append(f"warn:capital_below_requested:{available_cash:.2f}/{projected_size:.2f}")

        if reconciliation is None:
            ceiling = min_projection_mode(ceiling, ExecutionProjectionOutcome.shadow)
            reasons.append("warn:reconciliation_missing")
        elif reconciliation.manual_review_required or reconciliation.status.value != "aligned":
            ceiling = min_projection_mode(ceiling, ExecutionProjectionOutcome.shadow)
            reasons.append(f"warn:reconciliation:{reconciliation.status.value}")
            if reconciliation.manual_review_required:
                reasons.append("warn:reconciliation_manual_review_required")

        if venue_health is None:
            ceiling = min_projection_mode(ceiling, ExecutionProjectionOutcome.shadow)
            reasons.append("warn:venue_health_missing")
        elif not venue_health.healthy:
            degraded_mode = bool(venue_health.details.get("degraded_mode")) or "degraded" in venue_health.message.lower()
            if degraded_mode:
                ceiling = min_projection_mode(ceiling, ExecutionProjectionOutcome.shadow)
                reasons.append(f"warn:venue_degraded:{venue_health.message}")
            else:
                return ExecutionProjectionOutcome.blocked, [f"block:venue_unhealthy:{venue_health.message}"]

        return ceiling, reasons

    def _build_mode_reports(
        self,
        *,
        requested: ExecutionProjectionMode,
        authorized_ceiling: ExecutionProjectionOutcome,
        safety_ceiling: ExecutionProjectionOutcome,
        readiness: ExecutionReadiness | None,
        compliance: ExecutionComplianceSnapshot,
        capital_snapshot: CapitalLedgerSnapshot | None,
        reconciliation: ReconciliationReport | None,
        venue_health: VenueHealthReport | None,
    ) -> dict[ExecutionProjectionMode, ExecutionProjectionModeReport]:
        reports: dict[ExecutionProjectionMode, ExecutionProjectionModeReport] = {}
        for mode in (ExecutionProjectionMode.paper, ExecutionProjectionMode.shadow, ExecutionProjectionMode.live):
            effective = min_projection_mode(mode, authorized_ceiling, safety_ceiling)
            blockers: list[str] = []
            warnings: list[str] = []
            if effective == ExecutionProjectionOutcome.blocked:
                blockers.append(f"mode_blocked:{mode.value}")
            if mode == ExecutionProjectionMode.live and compliance.highest_authorized_mode != ExecutionProjectionOutcome.live:
                blockers.append(f"compliance_ceiling:{compliance.highest_authorized_mode.value}")
            if readiness is not None and readiness.manual_review_required:
                warnings.append("manual_review_required")
            if capital_snapshot is not None and capital_snapshot.equity <= 0.0:
                blockers.append("capital_equity_non_positive")
            if reconciliation is not None and reconciliation.manual_review_required:
                warnings.append("reconciliation_manual_review_required")
            if venue_health is not None and not venue_health.healthy:
                warnings.append(f"venue_health:{venue_health.message}")
            verdict = (
                ExecutionProjectionVerdict.blocked
                if effective == ExecutionProjectionOutcome.blocked
                else ExecutionProjectionVerdict.ready
                if mode == requested and effective == mode and not blockers
                else ExecutionProjectionVerdict.degraded
            )
            reports[mode] = ExecutionProjectionModeReport(
                requested_mode=mode,
                verdict=verdict,
                effective_mode=effective,
                blockers=self._dedupe(blockers),
                warnings=self._dedupe(warnings),
            )
        return reports

    def _anchor_at(
        self,
        *,
        readiness: ExecutionReadiness | None,
        compliance: ExecutionComplianceSnapshot,
        capital_snapshot: CapitalLedgerSnapshot | None,
        reconciliation: ReconciliationReport | None,
        venue_health: VenueHealthReport | None,
    ) -> datetime:
        anchors: list[datetime] = []
        compliance_anchor = _utc_datetime(compliance.created_at)
        if compliance_anchor is not None:
            anchors.append(compliance_anchor)
        if readiness is not None:
            readiness_anchor = _utc_datetime(readiness.created_at)
            if readiness_anchor is not None:
                anchors.append(readiness_anchor)
        if capital_snapshot is not None:
            capital_anchor = _utc_datetime(capital_snapshot.updated_at)
            if capital_anchor is not None:
                anchors.append(capital_anchor)
        if reconciliation is not None:
            reconciliation_anchor = _utc_datetime(reconciliation.created_at)
            if reconciliation_anchor is not None:
                anchors.append(reconciliation_anchor)
        if venue_health is not None:
            venue_health_anchor = _utc_datetime(venue_health.checked_at)
            if venue_health_anchor is not None:
                anchors.append(venue_health_anchor)
        return max(anchors) if anchors else _utc_now()

    def _expires_at(self, anchor_at: datetime) -> datetime:
        ttl = max(30.0, float(self.ttl_seconds))
        return anchor_at.replace(microsecond=0) + timedelta(seconds=ttl)

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        deduped: list[str] = []
        for value in values:
            if value not in deduped:
                deduped.append(value)
        return deduped


def _compliance_summary_text(
    *,
    requested_mode: ExecutionProjectionMode,
    allowed: bool,
    highest_authorized_mode: ExecutionProjectionOutcome,
    reasons: list[str],
    warnings: list[str],
) -> str:
    parts = [f"requested={requested_mode.value}", f"allowed={allowed}", f"highest_authorized={highest_authorized_mode.value}"]
    if reasons:
        parts.append("reasons=" + ",".join(reasons))
    if warnings:
        parts.append("warnings=" + ",".join(warnings))
    return "; ".join(parts)


def _highest_safe_mode(
    *,
    readiness: ExecutionReadiness | None,
    venue_health: VenueHealthReport | None,
    capital_snapshot: CapitalLedgerSnapshot | None,
    reconciliation: ReconciliationReport | None,
) -> ExecutionProjectionOutcome:
    if readiness is None or not readiness.can_materialize_trade_intent:
        return ExecutionProjectionOutcome.blocked

    ceiling = ExecutionProjectionOutcome.live
    if capital_snapshot is None:
        ceiling = min_projection_mode(ceiling, ExecutionProjectionOutcome.paper)
    else:
        available_cash = max(0.0, float(capital_snapshot.cash - capital_snapshot.reserved_cash))
        projected_size = max(0.0, float(readiness.size_usd))
        if available_cash <= 0.0:
            return ExecutionProjectionOutcome.blocked
        if projected_size > 0.0 and available_cash + 1e-9 < projected_size:
            ceiling = min_projection_mode(ceiling, ExecutionProjectionOutcome.paper)

    if reconciliation is None:
        ceiling = min_projection_mode(ceiling, ExecutionProjectionOutcome.shadow)
    elif reconciliation.manual_review_required or reconciliation.status.value != "aligned":
        ceiling = min_projection_mode(ceiling, ExecutionProjectionOutcome.shadow)

    if venue_health is None:
        ceiling = min_projection_mode(ceiling, ExecutionProjectionOutcome.shadow)
    elif not venue_health.healthy:
        degraded_mode = bool(venue_health.details.get("degraded_mode")) or "degraded" in venue_health.message.lower()
        if degraded_mode:
            ceiling = min_projection_mode(ceiling, ExecutionProjectionOutcome.shadow)
        else:
            return ExecutionProjectionOutcome.blocked

    return ceiling
