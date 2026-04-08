from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from pathlib import Path

if "prediction_markets" not in sys.modules:
    package = types.ModuleType("prediction_markets")
    package.__path__ = [str(Path(__file__).resolve().parents[2] / "prediction_markets")]
    sys.modules["prediction_markets"] = package

from prediction_markets.capital_ledger import CapitalLedgerSnapshot
from prediction_markets.models import ExecutionProjectionMode, MarketDescriptor, MarketStatus, VenueName, VenueType
from prediction_markets.runtime_guard import RuntimeGuardVerdict, build_runtime_guard_trace, monitor_runtime_guard


def _market() -> MarketDescriptor:
    return MarketDescriptor(
        market_id="pm_guard",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        title="Guard market",
        question="Will the guard pass?",
        status=MarketStatus.open,
        canonical_event_id="guard_event",
        resolution_source="https://example.com/resolution",
    )


def _ledger() -> CapitalLedgerSnapshot:
    return CapitalLedgerSnapshot(
        venue=VenueName.polymarket,
        cash=1_000.0,
        reserved_cash=0.0,
        realized_pnl=0.0,
        metadata={"equity_high_watermark": 1_000.0},
    )


def test_runtime_guard_blocks_without_human_approval_for_live() -> None:
    trace = build_runtime_guard_trace(
        run_id="run_guard_block",
        market=_market(),
        requested_mode=ExecutionProjectionMode.live,
        ledger_before=_ledger(),
        request_metadata={
            "human_approval_required_before_live": True,
            "human_approval_passed": False,
            "requested_mode": "live",
            "approval_actor": "operator",
        },
    )

    assert trace.verdict == RuntimeGuardVerdict.blocked
    assert trace.human_approval_required is True
    assert trace.human_approval_passed is False
    assert "human_approval_required_before_live" in trace.blocked_reasons
    assert trace.incident_runbook["runbook_id"] == "human_approval_required_before_live"
    assert trace.incident_runbook["recommended_action"] == "stay_dry_run"
    assert "human_approval_required" in trace.incident_alerts
    assert "approval" in trace.manual_review_categories
    assert "approval" in trace.metadata["manual_review_categories"]
    assert trace.metadata["human_approval_required_before_live"] is True
    assert trace.metadata["human_approval_passed"] is False


def test_runtime_guard_reports_ok_when_human_approval_is_recorded() -> None:
    trace = build_runtime_guard_trace(
        run_id="run_guard_ok",
        market=_market(),
        requested_mode=ExecutionProjectionMode.live,
        ledger_before=_ledger(),
        request_metadata={
            "human_approval_required_before_live": True,
            "human_approval_passed": True,
            "human_approval_actor": "operator",
            "human_approval_at": datetime(2026, 4, 8, tzinfo=timezone.utc).isoformat(),
            "requested_mode": "live",
        },
    )

    assert trace.verdict == RuntimeGuardVerdict.ok
    assert trace.human_approval_required is True
    assert trace.human_approval_passed is True
    assert trace.human_approval_reasons[0] == "human_approval_recorded"
    assert trace.incident_runbook["runbook_id"] == "runtime_guard_ok"
    assert trace.metadata["human_approval_passed"] is True


def test_runtime_guard_reports_kill_switch_alerts() -> None:
    trace = build_runtime_guard_trace(
        run_id="run_guard_kill_switch",
        market=_market(),
        requested_mode=ExecutionProjectionMode.paper,
        ledger_before=_ledger(),
        request_metadata={
            "kill_switch_triggered": True,
            "requested_mode": "paper",
        },
        kill_switch_triggered=True,
    )

    assert trace.verdict == RuntimeGuardVerdict.blocked
    assert trace.kill_switch_triggered is True
    assert "kill_switch_enabled" in trace.blocked_reasons
    assert "kill_switch" in trace.incident_alerts
    assert trace.incident_runbook["runbook_id"] == "runtime_guard_blocked"


def test_runtime_guard_blocks_on_compliance_auth_failure() -> None:
    trace = build_runtime_guard_trace(
        run_id="run_guard_auth_failure",
        market=_market(),
        requested_mode=ExecutionProjectionMode.live,
        ledger_before=_ledger(),
        request_metadata={
            "authorized": False,
            "compliance_approved": False,
            "auth_principal": "tester",
            "auth_scopes": ["prediction_markets:execute"],
        },
    )

    assert trace.verdict == RuntimeGuardVerdict.blocked
    assert "compliance_auth_failure" in trace.blocked_reasons
    assert trace.incident_runbook["runbook_id"] == "compliance_auth_failure"
    assert "compliance_auth_failure" in trace.incident_alerts


def test_runtime_guard_blocks_on_manipulation_suspicion() -> None:
    trace = build_runtime_guard_trace(
        run_id="run_guard_manipulation",
        market=_market(),
        requested_mode=ExecutionProjectionMode.live,
        ledger_before=_ledger(),
        request_metadata={
            "manipulation_guard_signal_only": True,
            "manipulation_guard_severity": "high",
        },
    )

    assert trace.verdict == RuntimeGuardVerdict.blocked
    assert "manipulation_suspicion" in trace.blocked_reasons
    assert trace.incident_runbook["runbook_id"] == "manipulation_suspicion"
    assert "manipulation_suspicion" in trace.incident_alerts


def test_runtime_guard_blocks_on_risk_thresholds_and_surfaces_explicit_reasons() -> None:
    trace = build_runtime_guard_trace(
        run_id="run_guard_thresholds",
        market=_market(),
        requested_mode=ExecutionProjectionMode.live,
        ledger_before=_ledger(),
        request_metadata={
            "requested_mode": "live",
            "snapshot_staleness_ms": 150_000,
            "snapshot_ttl_ms": 90_000,
            "snapshot_liquidity_usd": 500.0,
            "min_liquidity_usd": 1_000.0,
            "snapshot_depth_near_touch": 12.0,
            "min_depth_near_touch": 18.0,
            "snapshot_edge_after_fees_bps": 30.0,
            "min_edge_after_fees_bps": 35.0,
            "resolution_compatibility_score": 0.45,
            "min_resolution_compatibility_score": 0.60,
            "resolution_coherence_score": 0.40,
            "min_payout_compatibility_score": 0.70,
            "payout_compatibility_score": 0.50,
            "currency_compatibility_score": 0.55,
            "min_currency_compatibility_score": 0.70,
        },
    )

    assert trace.verdict == RuntimeGuardVerdict.blocked
    assert "snapshot_stale:150000/90000" in trace.blocked_reasons
    assert "liquidity_below_minimum:500.00/1000.00" in trace.blocked_reasons
    assert "depth_near_touch_below_minimum:12.00/18.00" in trace.blocked_reasons
    assert "edge_after_fees_below_minimum:30.00/35.00" in trace.blocked_reasons
    assert "resolution_compatibility_below_minimum:0.450/0.600" in trace.blocked_reasons
    assert "payout_compatibility_below_minimum:0.500/0.700" in trace.blocked_reasons
    assert "currency_compatibility_below_minimum:0.550/0.700" in trace.blocked_reasons
    assert trace.incident_runbook["runbook_id"] == "runtime_guard_blocked"
    assert trace.metadata["risk_thresholds"]["min_liquidity_usd"] == 1_000.0
    assert "data" in trace.manual_review_categories
    assert "resolution" in trace.manual_review_categories
    assert "market_data_quality" in trace.incident_alerts
    assert "edge_quality" in trace.incident_alerts
    assert "resolution_quality" in trace.incident_alerts


def test_runtime_guard_monitor_reports_recovery_after_blocked_trace() -> None:
    blocked_trace = build_runtime_guard_trace(
        run_id="run_guard_monitor",
        market=_market(),
        requested_mode=ExecutionProjectionMode.live,
        ledger_before=_ledger(),
        request_metadata={
            "human_approval_required_before_live": True,
            "human_approval_passed": False,
            "requested_mode": "live",
        },
    )
    ok_trace = build_runtime_guard_trace(
        run_id="run_guard_monitor",
        market=_market(),
        requested_mode=ExecutionProjectionMode.live,
        ledger_before=_ledger(),
        request_metadata={
            "human_approval_required_before_live": True,
            "human_approval_passed": True,
            "human_approval_actor": "operator",
            "requested_mode": "live",
        },
    )

    report = monitor_runtime_guard([blocked_trace, ok_trace], run_id="run_guard_monitor")

    assert report.trace_count == 2
    assert report.blocked_count == 1
    assert report.ok_count == 1
    assert report.latest_verdict == RuntimeGuardVerdict.ok
    assert report.recovery_required is True
    assert report.recovered is True
    assert report.shadow_ready is False
    assert report.incident_runbook["runbook_id"] == "runtime_guard_ok"
    assert report.summary.startswith("traces=2; ok=1; degraded=0; blocked=1")
    assert "recovered=True" in report.summary
