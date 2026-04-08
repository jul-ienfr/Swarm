from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from .capital_ledger import CapitalLedger, CapitalLedgerChange, CapitalLedgerStore
from .models import (
    CapitalLedgerSnapshot,
    DecisionAction,
    MarketDescriptor,
    MarketSnapshot,
    MarketRecommendationPacket,
    MarketStatus,
    TradeSide,
    VenueName,
)
from .paper_trading import PaperTradeSimulation, PaperTradeSimulator, PaperTradeStatus, PaperTradeStore
from .microstructure_lab import MicrostructureLab, MicrostructureReport
from .slippage_liquidity import SlippageLiquidityReport, SlippageLiquiditySimulator
from .paths import PredictionMarketPaths, default_prediction_market_paths
from .storage import save_json
from .runtime_guard import RuntimeGuardTrace, build_runtime_guard_trace


def _market_descriptor_from_snapshot(snapshot: MarketSnapshot) -> MarketDescriptor:
    return MarketDescriptor(
        market_id=snapshot.market_id,
        venue=snapshot.venue,
        venue_type=snapshot.venue_type,
        title=snapshot.title,
        question=snapshot.question,
        status=snapshot.status if snapshot.status != MarketStatus.unknown else MarketStatus.open,
        source_url=snapshot.source_url,
        canonical_event_id=snapshot.canonical_event_id,
        close_time=snapshot.close_time,
        resolution_source=snapshot.resolution_source,
        tags=list(snapshot.tags),
        metadata=dict(snapshot.metadata),
        raw=dict(snapshot.raw),
    )


def _projection_path(paths: PredictionMarketPaths, run_id: str) -> Path:
    return paths.run_dir(run_id) / "execution_projection.json"


def _normalize_alerts(*values: Any) -> list[str]:
    alerts: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            candidates = [value]
        else:
            candidates = list(value)
        for candidate in candidates:
            text = str(candidate).strip()
            if text and text not in alerts:
                alerts.append(text)
    return alerts


class ShadowExecutionIncident(BaseModel):
    schema_version: str = "v1"
    incident_id: str = Field(default_factory=lambda: f"shadow_inc_{uuid4().hex[:12]}")
    shadow_id: str
    run_id: str
    market_id: str
    venue: VenueName
    incident_kind: str = "shadow_execution_gate"
    summary: str = ""
    alerts: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    degraded_reasons: list[str] = Field(default_factory=list)
    execution_projection_id: str | None = None
    execution_projection_verdict: str | None = None
    runtime_guard_trace_id: str | None = None
    runtime_guard_verdict: str | None = None
    runtime_guard_runbook: dict[str, Any] = Field(default_factory=dict)
    gate: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ShadowExecutionResult(BaseModel):
    schema_version: str = "v1"
    shadow_id: str = Field(default_factory=lambda: f"shadow_{uuid4().hex[:12]}")
    run_id: str
    market_id: str
    venue: VenueName
    recommendation_id: str | None = None
    execution_projection_id: str | None = None
    execution_projection_verdict: str | None = None
    execution_projection_mode: str | None = None
    projection_gate_valid: bool = False
    would_trade: bool = False
    blocked_reason: str | None = None
    paper_trade: PaperTradeSimulation | None = None
    ledger_before: CapitalLedgerSnapshot
    ledger_after: CapitalLedgerSnapshot
    ledger_change: CapitalLedgerChange | None = None
    risk_flags: list[str] = Field(default_factory=list)
    incident_alerts: list[str] = Field(default_factory=list)
    incident_summary: str = ""
    incident_runbook: dict[str, Any] = Field(default_factory=dict)
    slippage_fit_status: str = "unknown"
    microstructure_fit_status: str = "unknown"
    market_fit_status: str = "unknown"
    market_fit_score: float = 0.0
    market_fit_reasons: list[str] = Field(default_factory=list)
    market_fit_report: dict[str, Any] | None = None
    runtime_guard_trace_id: str | None = None
    runtime_guard_verdict: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ShadowExecutionStore:
    def __init__(self, paths: PredictionMarketPaths | None = None, *, base_dir: str | Path | None = None) -> None:
        if paths is not None:
            self.paths = paths
        elif base_dir is not None:
            self.paths = PredictionMarketPaths(Path(base_dir))
        else:
            self.paths = default_prediction_market_paths()
        self.paths.ensure_layout()
        self.root = self.paths.root / "shadow_executions"
        self.root.mkdir(parents=True, exist_ok=True)
        self.incident_root = self.paths.root / "shadow_incidents"
        self.incident_root.mkdir(parents=True, exist_ok=True)

    def save(self, result: ShadowExecutionResult) -> Path:
        path = self.root / f"{result.shadow_id}.json"
        save_json(path, result)
        return path

    def load(self, shadow_id: str) -> ShadowExecutionResult:
        return ShadowExecutionResult.model_validate_json((self.root / f"{shadow_id}.json").read_text(encoding="utf-8"))

    def save_incident(self, incident: ShadowExecutionIncident) -> Path:
        path = self.incident_root / f"{incident.incident_id}.json"
        save_json(path, incident)
        return path

    def load_incident(self, incident_id: str) -> ShadowExecutionIncident:
        return ShadowExecutionIncident.model_validate_json((self.incident_root / f"{incident_id}.json").read_text(encoding="utf-8"))


@dataclass
class ShadowExecutionAdapter:
    paths: PredictionMarketPaths | None = None

    def __post_init__(self) -> None:
        self.paths = self.paths or default_prediction_market_paths()
        self.paths.ensure_layout()

    def resolve_execution_projection(
        self,
        recommendation: MarketRecommendationPacket,
        *,
        store: ShadowExecutionStore | None = None,
        execution_projection: ExecutionProjection | None = None,
    ) -> tuple[ExecutionProjection | None, Path | None]:
        from .execution_projection import ExecutionProjection

        if execution_projection is not None:
            return execution_projection, None
        resolved_paths = store.paths if store is not None else self.paths
        projection_path = _projection_path(resolved_paths, recommendation.run_id)
        if projection_path.exists():
            return ExecutionProjection.load(projection_path), projection_path
        return None, projection_path

    def build_runtime_guard(
        self,
        *,
        recommendation: MarketRecommendationPacket,
        snapshot: MarketSnapshot,
        ledger: CapitalLedgerSnapshot,
        projection: ExecutionProjection,
    ) -> RuntimeGuardTrace:
        market = _market_descriptor_from_snapshot(snapshot)
        projection_metadata = dict(projection.metadata)
        requested_mode = projection.requested_mode
        kill_switch_triggered = bool(
            projection_metadata.get("kill_switch_triggered")
            or any("kill_switch" in reason for reason in projection.blocking_reasons)
        )
        return build_runtime_guard_trace(
            run_id=recommendation.run_id,
            market=market,
            requested_mode=requested_mode,
            ledger_before=ledger,
            request_metadata={
                **projection_metadata,
                "recommendation_id": recommendation.recommendation_id,
                "execution_projection_id": projection.projection_id,
                "execution_projection_verdict": projection.projection_verdict.value,
                "execution_projection_mode": projection.projected_mode.value,
                "requested_mode": requested_mode.value,
                "requested_run_mode": "shadow",
            },
            reconciliation_drift_usd=projection_metadata.get("reconciliation_drift_usd"),
            kill_switch_triggered=kill_switch_triggered,
        )

    def build_gate(
        self,
        *,
        projection: Any | None,
        runtime_guard: RuntimeGuardTrace | None,
        recommendation: MarketRecommendationPacket,
    ) -> Any:
        from .execution_projection import (
            ExecutionProjectionOutcome,
            ExecutionProjectionVerdict,
            ShadowExecutionProjectionGate,
            build_shadow_execution_projection_gate,
        )

        if projection is None:
            return ShadowExecutionProjectionGate(
                projection_id=f"missing_{recommendation.run_id}",
                run_id=recommendation.run_id,
                market_id=recommendation.market_id,
                venue=recommendation.venue.value,
                projection_verdict=ExecutionProjectionVerdict.blocked,
                projected_mode=ExecutionProjectionOutcome.blocked,
                valid=False,
                expired=False,
                stale=False,
                manual_review_required=True,
                blocked_reasons=["execution_projection_missing"],
                degraded_reasons=[],
                incident_alerts=["execution_projection_missing"],
                incident_summary="shadow gate blocked: execution projection missing",
                incident_runbook={
                    "runbook_id": "shadow_execution_projection_missing",
                    "runbook_kind": "incident",
                    "summary": "Shadow execution requires an ExecutionProjection persisted for the run.",
                    "recommended_action": "recompute_projection",
                    "owner": "operator",
                    "priority": "high",
                    "status": "blocked",
                    "trigger_reasons": ["execution_projection_missing"],
                    "next_steps": [
                        "Rebuild the execution projection for this run before shadow execution.",
                        "Verify the run artifacts are persisted before materializing shadow.",
                    ],
                    "signals": {
                        "alerts": ["execution_projection_missing"],
                        "blocked_reasons": ["execution_projection_missing"],
                        "degraded_reasons": [],
                    },
                },
                metadata={"execution_projection_path": None},
        )
        return build_shadow_execution_projection_gate(projection, runtime_guard=runtime_guard)

    def _market_fit_reference_price(self, recommendation: MarketRecommendationPacket, snapshot: MarketSnapshot) -> float:
        position_side = recommendation.side or TradeSide.yes
        candidates: list[float] = []

        def add_candidate(value: float | None, *, mirror: bool = False) -> None:
            if value is None:
                return
            price = float(value)
            if mirror:
                price = 1.0 - price
            if price > 0.0:
                candidates.append(max(1e-6, min(1.0, round(price, 6))))

        add_candidate(recommendation.price_reference)
        add_candidate(snapshot.market_implied_probability, mirror=position_side == TradeSide.no)
        add_candidate(snapshot.midpoint_yes, mirror=position_side == TradeSide.no)
        add_candidate(snapshot.price_yes, mirror=position_side == TradeSide.no)
        add_candidate(snapshot.price_no, mirror=position_side != TradeSide.no)
        return candidates[0] if candidates else 0.5

    def build_market_fit_reports(
        self,
        *,
        recommendation: MarketRecommendationPacket,
        snapshot: MarketSnapshot,
        ledger: CapitalLedgerSnapshot,
        requested_stake: float,
    ) -> tuple[SlippageLiquidityReport, MicrostructureReport, dict[str, Any]]:
        position_side = recommendation.side or TradeSide.yes
        reference_price = self._market_fit_reference_price(recommendation, snapshot)
        requested_quantity = max(0.0, requested_stake / max(reference_price, 1e-6))
        limit_price = recommendation.price_reference if recommendation.price_reference is not None else reference_price

        slippage_report = SlippageLiquiditySimulator(fee_bps=0.0, max_slippage_bps=250.0).simulate(
            snapshot,
            position_side=position_side,
            execution_side=TradeSide.buy,
            requested_quantity=requested_quantity,
            limit_price=limit_price,
            run_id=recommendation.run_id,
            market_id=recommendation.market_id,
            venue=recommendation.venue,
            metadata={
                "shadow_execution": True,
                "source": "shadow_execution_market_fit",
                "recommended_stake": requested_stake,
                "reference_price": reference_price,
            },
        )
        microstructure_report = MicrostructureLab().simulate(
            snapshot,
            position_side=position_side,
            execution_side=TradeSide.buy,
            requested_quantity=requested_quantity,
            capital_available_usd=ledger.cash,
            capital_locked_usd=ledger.reserved_cash,
            limit_price=limit_price,
            metadata={
                "shadow_execution": True,
                "source": "shadow_execution_market_fit",
                "recommended_stake": requested_stake,
                "reference_price": reference_price,
            },
        )
        fit_summary = self.build_market_fit_summary(
            slippage_report=slippage_report,
            microstructure_report=microstructure_report,
            requested_stake=requested_stake,
            reference_price=reference_price,
        )
        return slippage_report, microstructure_report, fit_summary

    def build_market_fit_summary(
        self,
        *,
        slippage_report: SlippageLiquidityReport,
        microstructure_report: MicrostructureReport,
        requested_stake: float,
        reference_price: float,
    ) -> dict[str, Any]:
        blocked_statuses = {
            "no_liquidity",
            "queue_miss",
            "spread_collapse",
            "capital_locked",
            "limit_price_excludes_orderbook",
            "rejected",
            "slippage_guard_triggered",
        }
        slippage_status = slippage_report.market_fit_status
        microstructure_status = microstructure_report.market_fit_status
        market_fit_reasons = list(dict.fromkeys([*slippage_report.market_fit_reasons, *microstructure_report.market_fit_reasons]))
        shadow_eligible = slippage_report.shadow_eligible and microstructure_report.shadow_eligible
        if not shadow_eligible and (slippage_status in blocked_statuses or microstructure_status in blocked_statuses):
            market_fit_status = "mismatch"
        elif slippage_status == microstructure_status:
            market_fit_status = slippage_status
        elif "partial_fit" in {slippage_status, microstructure_status}:
            market_fit_status = "partial_fit"
        elif "synthetic_reference" in {slippage_status, microstructure_status}:
            market_fit_status = "synthetic_reference"
        else:
            market_fit_status = "fit" if shadow_eligible else "mismatch"

        market_fit_score = round(min(slippage_report.market_fit_score, microstructure_report.market_fit_score), 6)
        market_fit_report = {
            "requested_stake": requested_stake,
            "reference_price": reference_price,
            "shadow_eligible": shadow_eligible,
            "slippage": slippage_report.to_execution_metadata(),
            "microstructure": microstructure_report.to_execution_metadata(),
        }
        return {
            "slippage_fit_status": slippage_status,
            "microstructure_fit_status": microstructure_status,
            "market_fit_status": market_fit_status,
            "market_fit_score": market_fit_score,
            "market_fit_reasons": market_fit_reasons,
            "shadow_eligible": shadow_eligible,
            "market_fit_report": market_fit_report,
        }

    def _build_paper_shadow_divergence(
        self,
        *,
        paper_trade: PaperTradeSimulation | None,
        market_fit_summary: dict[str, Any],
    ) -> dict[str, Any]:
        shadow_eligible = bool(market_fit_summary.get("shadow_eligible"))
        shadow_market_fit_status = str(market_fit_summary.get("market_fit_status", "unknown"))
        slippage_fit_status = str(market_fit_summary.get("slippage_fit_status", "unknown"))
        microstructure_fit_status = str(market_fit_summary.get("microstructure_fit_status", "unknown"))
        reason_codes = _normalize_alerts(market_fit_summary.get("market_fit_reasons", []))
        if paper_trade is None:
            divergence_class = "shadow_blocked_before_paper" if not shadow_eligible else "shadow_projection_only"
            paper_postmortem: dict[str, Any] | None = None
        else:
            paper_postmortem = paper_trade.postmortem().model_dump(mode="json")
            reason_codes = _normalize_alerts(reason_codes, paper_postmortem.get("notes", []))
            paper_no_trade_zone = bool(paper_postmortem.get("no_trade_zone"))
            paper_recommendation = str(paper_postmortem.get("recommendation", "hold"))
            if paper_no_trade_zone and shadow_eligible:
                divergence_class = "paper_no_trade_shadow_tradeable"
            elif paper_no_trade_zone and not shadow_eligible:
                divergence_class = "aligned_no_trade"
            elif not paper_no_trade_zone and not shadow_eligible:
                divergence_class = "paper_tradeable_shadow_blocked"
            else:
                divergence_class = "aligned_tradeable"
            if paper_postmortem.get("stale_blocked"):
                reason_codes.append("stale_blocked")
            if paper_trade.metadata.get("slippage_guard_triggered"):
                reason_codes.append("slippage_guard_triggered")
            if paper_no_trade_zone:
                reason_codes.append("paper_no_trade_zone")
            if paper_recommendation == "no_trade":
                reason_codes.append("paper_recommendation_no_trade")
        reason_codes = _normalize_alerts(reason_codes)
        if paper_trade is None:
            paper_status = None
            paper_no_trade_zone = None
            paper_recommendation = None
            paper_fill_rate = None
            paper_slippage_bps = None
        else:
            paper_status = paper_trade.status.value
            paper_no_trade_zone = bool(paper_postmortem.get("no_trade_zone"))
            paper_recommendation = str(paper_postmortem.get("recommendation", "hold"))
            paper_fill_rate = float(paper_postmortem.get("fill_rate", 0.0) or 0.0)
            paper_slippage_bps = paper_trade.slippage_bps
        return {
            "divergence_class": divergence_class,
            "paper_trade_status": paper_status,
            "paper_no_trade_zone": paper_no_trade_zone,
            "paper_recommendation": paper_recommendation,
            "paper_fill_rate": paper_fill_rate,
            "paper_slippage_bps": paper_slippage_bps,
            "shadow_eligible": shadow_eligible,
            "shadow_market_fit_status": shadow_market_fit_status,
            "slippage_fit_status": slippage_fit_status,
            "microstructure_fit_status": microstructure_fit_status,
            "reason_codes": reason_codes,
            "paper_trade_reclassified_no_trade": bool(
                paper_trade is not None
                and paper_trade.status in {PaperTradeStatus.filled, PaperTradeStatus.partial}
                and paper_no_trade_zone
            ),
            "paper_trade_postmortem": paper_postmortem,
        }


@dataclass
class ShadowExecutionEngine:
    starting_cash: float = 1000.0
    fee_bps: float = 25.0
    default_stake: float = 10.0
    paper_simulator: PaperTradeSimulator = field(default_factory=PaperTradeSimulator)
    adapter: ShadowExecutionAdapter = field(default_factory=ShadowExecutionAdapter)

    def run(
        self,
        recommendation: MarketRecommendationPacket,
        snapshot: MarketSnapshot,
        *,
        ledger: CapitalLedgerSnapshot | None = None,
        stake: float | None = None,
        persist: bool = False,
        store: ShadowExecutionStore | None = None,
        execution_projection: ExecutionProjection | None = None,
        runtime_guard: RuntimeGuardTrace | None = None,
    ) -> ShadowExecutionResult:
        shadow_store = store or ShadowExecutionStore()
        ledger_engine = CapitalLedger.from_snapshot(
            ledger
            or CapitalLedgerSnapshot(
                venue=recommendation.venue,
                cash=self.starting_cash,
                reserved_cash=0.0,
                metadata={"source": "shadow_default"},
            )
        )
        ledger_before = ledger_engine.current_snapshot()
        risk_flags: list[str] = []

        projection, projection_path = self.adapter.resolve_execution_projection(
            recommendation,
            store=shadow_store,
            execution_projection=execution_projection,
        )
        resolved_runtime_guard = runtime_guard
        if projection is not None and resolved_runtime_guard is None:
            resolved_runtime_guard = self.adapter.build_runtime_guard(
                recommendation=recommendation,
                snapshot=snapshot,
                ledger=ledger_before,
                projection=projection,
            )
        gate = self.adapter.build_gate(
            projection=projection,
            runtime_guard=resolved_runtime_guard,
            recommendation=recommendation,
        )

        if not gate.valid:
            projection_ref = gate.projection_id if projection is None else projection.projection_id
            risk_flags.extend([*gate.blocked_reasons, *gate.incident_alerts] or ["shadow_gate_blocked"])
            result = ShadowExecutionResult(
                run_id=recommendation.run_id,
                market_id=recommendation.market_id,
                venue=recommendation.venue,
                recommendation_id=recommendation.recommendation_id,
                execution_projection_id=projection_ref,
                execution_projection_verdict=gate.projection_verdict.value,
                execution_projection_mode=gate.projected_mode.value,
                projection_gate_valid=False,
                would_trade=False,
                blocked_reason=gate.incident_summary or "shadow gate blocked",
                ledger_before=ledger_before,
                ledger_after=ledger_before.model_copy(deep=True),
                risk_flags=list(dict.fromkeys(risk_flags)),
                incident_alerts=list(gate.incident_alerts),
                incident_summary=gate.incident_summary,
                incident_runbook=gate.incident_runbook,
                runtime_guard_trace_id=None if resolved_runtime_guard is None else resolved_runtime_guard.trace_id,
                runtime_guard_verdict=None if resolved_runtime_guard is None else resolved_runtime_guard.verdict.value,
                metadata={
                    "shadow_execution_adapter": "execution_projection_gate",
                    "shadow_mode": "blocked",
                    "execution_projection_id": projection_ref,
                    "execution_projection_path": None if projection_path is None else str(projection_path),
                    "execution_projection_verdict": gate.projection_verdict.value,
                    "execution_projection_mode": gate.projected_mode.value,
                    "incident_alerts": list(gate.incident_alerts),
                    "blocked_reasons": list(gate.blocked_reasons),
                    "incident_summary": gate.incident_summary,
                    "incident_runbook": gate.incident_runbook,
                    "projection_gate_valid": False,
                    "runtime_guard_trace_id": None if resolved_runtime_guard is None else resolved_runtime_guard.trace_id,
                    "runtime_guard_verdict": None if resolved_runtime_guard is None else resolved_runtime_guard.verdict.value,
                },
            )
            return self._persist_if_needed(result, persist=persist, store=shadow_store)

        if recommendation.action != DecisionAction.bet or recommendation.side not in {TradeSide.yes, TradeSide.no}:
            risk_flags.append("no_live_trade")
            result = ShadowExecutionResult(
                run_id=recommendation.run_id,
                market_id=recommendation.market_id,
                venue=recommendation.venue,
                recommendation_id=recommendation.recommendation_id,
                execution_projection_id=None if projection is None else projection.projection_id,
                execution_projection_verdict=None if projection is None else projection.projection_verdict.value,
                execution_projection_mode=None if projection is None else projection.projected_mode.value,
                projection_gate_valid=gate.valid,
                would_trade=False,
                blocked_reason="recommendation does not call for a bet",
                ledger_before=ledger_before,
                ledger_after=ledger_before.model_copy(deep=True),
                risk_flags=risk_flags,
                incident_alerts=list(gate.incident_alerts),
                incident_summary=gate.incident_summary,
                incident_runbook=gate.incident_runbook,
                runtime_guard_trace_id=None if resolved_runtime_guard is None else resolved_runtime_guard.trace_id,
                runtime_guard_verdict=None if resolved_runtime_guard is None else resolved_runtime_guard.verdict.value,
                metadata={
                    "shadow_execution_adapter": "execution_projection_gate",
                    "shadow_mode": "skip",
                    "execution_projection_id": gate.projection_id if projection is None else projection.projection_id,
                    "execution_projection_path": None if projection_path is None else str(projection_path),
                    "execution_projection_verdict": None if projection is None else projection.projection_verdict.value,
                    "execution_projection_mode": None if projection is None else projection.projected_mode.value,
                    "incident_alerts": list(gate.incident_alerts),
                    "blocked_reasons": list(gate.blocked_reasons),
                    "incident_summary": gate.incident_summary,
                    "incident_runbook": gate.incident_runbook,
                    "projection_gate_valid": gate.valid,
                    "runtime_guard_trace_id": None if resolved_runtime_guard is None else resolved_runtime_guard.trace_id,
                    "runtime_guard_verdict": None if resolved_runtime_guard is None else resolved_runtime_guard.verdict.value,
                },
            )
            return self._persist_if_needed(result, persist=persist, store=shadow_store)

        requested_stake = float(stake if stake is not None else self.default_stake)
        slippage_report, microstructure_report, market_fit_summary = self.adapter.build_market_fit_reports(
            recommendation=recommendation,
            snapshot=snapshot,
            ledger=ledger_before,
            requested_stake=requested_stake,
        )

        if not market_fit_summary["shadow_eligible"]:
            risk_flags.extend(["market_fit_mismatch", *market_fit_summary["market_fit_reasons"]])
            paper_shadow_divergence = self.adapter._build_paper_shadow_divergence(
                paper_trade=None,
                market_fit_summary=market_fit_summary,
            )
            blocked_summary = (
                "shadow execution blocked: simulator does not match market"
                f" | divergence={paper_shadow_divergence['divergence_class']}"
            )
            result = ShadowExecutionResult(
                run_id=recommendation.run_id,
                market_id=recommendation.market_id,
                venue=recommendation.venue,
                recommendation_id=recommendation.recommendation_id,
                execution_projection_id=None if projection is None else projection.projection_id,
                execution_projection_verdict=None if projection is None else projection.projection_verdict.value,
                execution_projection_mode=None if projection is None else projection.projected_mode.value,
                projection_gate_valid=gate.valid,
                would_trade=False,
                blocked_reason="shadow simulator does not match market",
                ledger_before=ledger_before,
                ledger_after=ledger_before.model_copy(deep=True),
                risk_flags=list(dict.fromkeys(risk_flags)),
                incident_alerts=_normalize_alerts(
                    gate.incident_alerts,
                    ["shadow_simulator_market_fit_mismatch", *market_fit_summary["market_fit_reasons"]],
                    [f"paper_shadow_divergence:{paper_shadow_divergence['divergence_class']}"],
                ),
                incident_summary=blocked_summary,
                incident_runbook={
                    "runbook_id": "shadow_execution_market_fit_mismatch",
                    "runbook_kind": "incident",
                    "summary": "Shadow execution requires the simulator to match the market before any shadow trade is allowed.",
                    "recommended_action": "review_simulator_and_market_fit",
                    "owner": "operator",
                    "priority": "high",
                    "status": "blocked",
                    "trigger_reasons": ["market_fit_mismatch", *market_fit_summary["market_fit_reasons"]],
                    "next_steps": [
                        "Review the slippage and microstructure reports for the current market snapshot.",
                        "Do not allow shadow execution until both reports are shadow eligible.",
                    ],
                    "signals": {
                        "alerts": _normalize_alerts(
                            gate.incident_alerts,
                            ["shadow_simulator_market_fit_mismatch", *market_fit_summary["market_fit_reasons"]],
                        ),
                        "blocked_reasons": list(dict.fromkeys(risk_flags)),
                        "degraded_reasons": list(dict.fromkeys(market_fit_summary["market_fit_reasons"])),
                    },
                },
                slippage_fit_status=market_fit_summary["slippage_fit_status"],
                microstructure_fit_status=market_fit_summary["microstructure_fit_status"],
                market_fit_status=market_fit_summary["market_fit_status"],
                market_fit_score=market_fit_summary["market_fit_score"],
                market_fit_reasons=market_fit_summary["market_fit_reasons"],
                market_fit_report=market_fit_summary["market_fit_report"],
                runtime_guard_trace_id=None if resolved_runtime_guard is None else resolved_runtime_guard.trace_id,
                runtime_guard_verdict=None if resolved_runtime_guard is None else resolved_runtime_guard.verdict.value,
                metadata={
                    "recommended_stake": requested_stake,
                    "recommendation_action": recommendation.action.value,
                    "recommendation_side": None if recommendation.side is None else recommendation.side.value,
                    "shadow_execution_adapter": "execution_projection_gate",
                    "shadow_mode": "blocked",
                    "execution_projection_id": None if projection is None else projection.projection_id,
                    "execution_projection_path": None if projection_path is None else str(projection_path),
                    "execution_projection_verdict": None if projection is None else projection.projection_verdict.value,
                    "execution_projection_mode": None if projection is None else projection.projected_mode.value,
                    "incident_alerts": list(
                        _normalize_alerts(
                            gate.incident_alerts,
                            ["shadow_simulator_market_fit_mismatch"],
                            [f"paper_shadow_divergence:{paper_shadow_divergence['divergence_class']}"],
                        )
                    ),
                    "blocked_reasons": list(dict.fromkeys(risk_flags)),
                    "incident_summary": blocked_summary,
                    "incident_runbook": {
                        "runbook_id": "shadow_execution_market_fit_mismatch",
                        "status": "blocked",
                    },
                    "projection_gate_valid": gate.valid,
                    "runtime_guard_trace_id": None if resolved_runtime_guard is None else resolved_runtime_guard.trace_id,
                    "runtime_guard_verdict": None if resolved_runtime_guard is None else resolved_runtime_guard.verdict.value,
                    "market_fit_status": market_fit_summary["market_fit_status"],
                    "market_fit_score": market_fit_summary["market_fit_score"],
                    "market_fit_reasons": market_fit_summary["market_fit_reasons"],
                    "market_fit_report": market_fit_summary["market_fit_report"],
                    "slippage_fit_status": market_fit_summary["slippage_fit_status"],
                    "microstructure_fit_status": market_fit_summary["microstructure_fit_status"],
                    "paper_shadow_divergence": paper_shadow_divergence,
                },
            )
            return self._persist_if_needed(result, persist=persist, store=shadow_store)

        paper_trade = self.paper_simulator.simulate_from_recommendation(
            snapshot,
            recommendation_action=recommendation.action,
            side=recommendation.side,
            stake=requested_stake,
            run_id=recommendation.run_id,
            limit_price=recommendation.price_reference,
            metadata={
                "recommendation_confidence": recommendation.confidence,
                "recommendation_edge_bps": recommendation.edge_bps,
            },
        )
        if paper_trade.status == PaperTradeStatus.partial:
            risk_flags.append("partial_fill")
        if abs(paper_trade.slippage_bps) > self.paper_simulator.max_slippage_bps:
            risk_flags.append("high_slippage")
        if recommendation.confidence < 0.6:
            risk_flags.append("low_confidence")
        paper_shadow_divergence = self.adapter._build_paper_shadow_divergence(
            paper_trade=paper_trade,
            market_fit_summary=market_fit_summary,
        )
        if paper_shadow_divergence["divergence_class"] not in {"aligned_tradeable", "aligned_no_trade"}:
            risk_flags.append(f"paper_shadow_divergence:{paper_shadow_divergence['divergence_class']}")
        if paper_shadow_divergence["paper_trade_reclassified_no_trade"]:
            risk_flags.append("paper_reclassified_no_trade")
        incident_summary = gate.incident_summary
        if paper_shadow_divergence["divergence_class"] not in {"aligned_tradeable", "aligned_no_trade"}:
            incident_summary = (
                f"{gate.incident_summary or 'shadow execution completed'}"
                f" | divergence={paper_shadow_divergence['divergence_class']}"
            )
        incident_alerts = list(gate.incident_alerts)
        if paper_shadow_divergence["divergence_class"] not in {"aligned_tradeable", "aligned_no_trade"}:
            incident_alerts = _normalize_alerts(
                incident_alerts,
                [f"paper_shadow_divergence:{paper_shadow_divergence['divergence_class']}"],
            )

        mark_price = snapshot.market_implied_probability
        if mark_price is None:
            mark_price = snapshot.midpoint_yes
        if mark_price is None:
            mark_price = paper_trade.reference_price
        ledger_change = ledger_engine.apply_paper_trade(
            paper_trade,
            mark_price=mark_price,
        )
        ledger_after = ledger_engine.current_snapshot()
        result = ShadowExecutionResult(
            run_id=recommendation.run_id,
            market_id=recommendation.market_id,
            venue=recommendation.venue,
            recommendation_id=recommendation.recommendation_id,
            execution_projection_id=None if projection is None else projection.projection_id,
            execution_projection_verdict=None if projection is None else projection.projection_verdict.value,
            execution_projection_mode=None if projection is None else projection.projected_mode.value,
            projection_gate_valid=gate.valid,
            would_trade=True,
            paper_trade=paper_trade,
            ledger_before=ledger_before,
            ledger_after=ledger_after,
            ledger_change=ledger_change,
            risk_flags=risk_flags,
            incident_alerts=incident_alerts,
            incident_summary=incident_summary,
            incident_runbook=gate.incident_runbook,
            slippage_fit_status=market_fit_summary["slippage_fit_status"],
            microstructure_fit_status=market_fit_summary["microstructure_fit_status"],
            market_fit_status=market_fit_summary["market_fit_status"],
            market_fit_score=market_fit_summary["market_fit_score"],
            market_fit_reasons=market_fit_summary["market_fit_reasons"],
            market_fit_report=market_fit_summary["market_fit_report"],
            runtime_guard_trace_id=None if resolved_runtime_guard is None else resolved_runtime_guard.trace_id,
            runtime_guard_verdict=None if resolved_runtime_guard is None else resolved_runtime_guard.verdict.value,
            metadata={
                "recommended_stake": requested_stake,
                "recommendation_action": recommendation.action.value,
                "recommendation_side": None if recommendation.side is None else recommendation.side.value,
                "shadow_execution_adapter": "execution_projection_gate",
                "execution_projection_id": None if projection is None else projection.projection_id,
                "execution_projection_path": None if projection_path is None else str(projection_path),
                "execution_projection_verdict": None if projection is None else projection.projection_verdict.value,
                "execution_projection_mode": None if projection is None else projection.projected_mode.value,
                "incident_alerts": list(incident_alerts),
                "blocked_reasons": list(gate.blocked_reasons),
                "incident_summary": gate.incident_summary,
                "incident_runbook": gate.incident_runbook,
                "projection_gate_valid": gate.valid,
                "runtime_guard_trace_id": None if resolved_runtime_guard is None else resolved_runtime_guard.trace_id,
                "runtime_guard_verdict": None if resolved_runtime_guard is None else resolved_runtime_guard.verdict.value,
                "market_fit_status": market_fit_summary["market_fit_status"],
                "market_fit_score": market_fit_summary["market_fit_score"],
                "market_fit_reasons": market_fit_summary["market_fit_reasons"],
                "market_fit_report": market_fit_summary["market_fit_report"],
                "slippage_fit_status": market_fit_summary["slippage_fit_status"],
                "microstructure_fit_status": market_fit_summary["microstructure_fit_status"],
                "paper_trade_postmortem": paper_trade.postmortem().model_dump(mode="json"),
                "paper_shadow_divergence": paper_shadow_divergence,
            },
        )
        return self._persist_if_needed(result, persist=persist, store=shadow_store)

    def _persist_if_needed(
        self,
        result: ShadowExecutionResult,
        *,
        persist: bool,
        store: ShadowExecutionStore | None,
    ) -> ShadowExecutionResult:
        if not persist:
            return result
        shadow_store = store or ShadowExecutionStore()
        shadow_store.save(result)
        paper_trade_postmortem = result.paper_trade.postmortem() if result.paper_trade is not None else None
        divergence = dict(result.metadata.get("paper_shadow_divergence") or {})
        should_log_incident = bool(result.incident_alerts) or bool(result.risk_flags) or (
            result.blocked_reason is not None and result.blocked_reason != "recommendation does not call for a bet"
        )
        if paper_trade_postmortem is not None and paper_trade_postmortem.no_trade_zone:
            should_log_incident = True
        if should_log_incident:
            degraded_reasons = list(result.risk_flags)
            if paper_trade_postmortem is not None and paper_trade_postmortem.no_trade_zone:
                degraded_reasons = _normalize_alerts(
                    degraded_reasons,
                    ["paper_no_trade_zone", *paper_trade_postmortem.notes],
                    divergence.get("reason_codes", []),
                )
            shadow_store.save_incident(
                ShadowExecutionIncident(
                    shadow_id=result.shadow_id,
                    run_id=result.run_id,
                    market_id=result.market_id,
                    venue=result.venue,
                    summary=result.incident_summary or result.blocked_reason or "shadow execution incident",
                    alerts=list(result.incident_alerts),
                    blocked_reasons=list(result.risk_flags),
                    degraded_reasons=degraded_reasons,
                    execution_projection_id=result.execution_projection_id,
                    execution_projection_verdict=result.execution_projection_verdict,
                    runtime_guard_trace_id=result.runtime_guard_trace_id,
                    runtime_guard_verdict=result.runtime_guard_verdict,
                    runtime_guard_runbook=dict(result.incident_runbook),
                    gate={
                        "valid": result.projection_gate_valid,
                        "blocked_reason": result.blocked_reason,
                    },
                    metadata=dict(result.metadata),
                )
            )
        if result.paper_trade is not None:
            PaperTradeStore(shadow_store.paths).save(result.paper_trade)
        CapitalLedgerStore(shadow_store.paths).save_snapshot(result.ledger_after)
        return result
