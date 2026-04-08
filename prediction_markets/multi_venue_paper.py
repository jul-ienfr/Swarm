from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Sequence
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from .execution_edge import ArbPlanLeg
from .market_execution import MarketExecutionMode
from .cross_venue import CrossVenueTaxonomy
from .models import DecisionAction, MarketDescriptor, MarketSnapshot, TradeSide, VenueName, _stable_content_hash, _normalized_text
from .multi_venue_executor import MultiVenueExecutionPlan, MultiVenueExecutionReport
from .paper_trading import PaperTradeSimulation, PaperTradeSimulator, PaperTradeStatus


class MultiVenuePaperLegResult(BaseModel):
    schema_version: str = "v1"
    leg_result_id: str = Field(default_factory=lambda: f"mvpleg_{uuid4().hex[:12]}")
    plan_id: str
    candidate_id: str
    comparison_id: str
    canonical_event_id: str
    leg_id: str | None = None
    market_id: str
    venue: VenueName
    execution_side: TradeSide
    position_side: TradeSide
    requested_notional_usd: float = 0.0
    allocated_notional_usd: float = 0.0
    snapshot_id: str | None = None
    snapshot_available: bool = False
    paper_trade: PaperTradeSimulation | None = None
    paper_trade_status: PaperTradeStatus = PaperTradeStatus.skipped
    mark_price: float | None = None
    spread_bps: float | None = None
    gross_pnl_usd: float = 0.0
    fee_paid_usd: float = 0.0
    net_pnl_usd: float = 0.0
    fill_rate: float = 0.0
    partial_fill_rate: float = 0.0
    slippage_bps: float = 0.0
    legging_risk: bool = False
    legging_risk_reasons: list[str] = Field(default_factory=list)
    stale_blocked: bool = False
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "MultiVenuePaperLegResult":
        self.plan_id = _normalized_text(self.plan_id)
        self.candidate_id = _normalized_text(self.candidate_id)
        self.comparison_id = _normalized_text(self.comparison_id)
        self.canonical_event_id = _normalized_text(self.canonical_event_id)
        self.market_id = _normalized_text(self.market_id)
        self.notes = _dedupe(self.notes)
        self.legging_risk_reasons = _dedupe(self.legging_risk_reasons)
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        return self


class MultiVenuePaperPlanResult(BaseModel):
    schema_version: str = "v1"
    paper_plan_id: str = Field(default_factory=lambda: f"mvpp_{uuid4().hex[:12]}")
    execution_plan_id: str
    candidate_id: str
    comparison_id: str
    canonical_event_id: str
    route: str = "comparison_only"
    tradeable: bool = False
    manual_review_required: bool = True
    taxonomy: CrossVenueTaxonomy = CrossVenueTaxonomy.comparison_only
    execution_filter_reason_codes: list[str] = Field(default_factory=list)
    plan_market_ids: list[str] = Field(default_factory=list)
    execution_market_ids: list[str] = Field(default_factory=list)
    requested_notional_usd: float = 0.0
    allocated_notional_usd: float = 0.0
    simulated_notional_usd: float = 0.0
    paper_simulated: bool = False
    snapshot_coverage: float = 0.0
    simulated_leg_count: int = 0
    skipped_leg_count: int = 0
    filled_leg_count: int = 0
    partial_leg_count: int = 0
    rejected_leg_count: int = 0
    gross_pnl_usd: float = 0.0
    fee_paid_usd: float = 0.0
    net_pnl_usd: float = 0.0
    fill_rate: float = 0.0
    partial_fill_rate: float = 0.0
    stale_block_count: int = 0
    stale_block_rate: float = 0.0
    hedge_completion_rate: float = 0.0
    has_arb_plan: bool = False
    legging_loss_usd: float = 0.0
    average_slippage_bps: float = 0.0
    max_abs_slippage_bps: float = 0.0
    legging_risk: bool = False
    legging_risk_reasons: list[str] = Field(default_factory=list)
    legs: list[MultiVenuePaperLegResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "MultiVenuePaperPlanResult":
        self.execution_plan_id = _normalized_text(self.execution_plan_id)
        self.candidate_id = _normalized_text(self.candidate_id)
        self.comparison_id = _normalized_text(self.comparison_id)
        self.canonical_event_id = _normalized_text(self.canonical_event_id)
        self.route = _normalized_text(self.route) or "comparison_only"
        self.execution_filter_reason_codes = _dedupe(self.execution_filter_reason_codes)
        self.plan_market_ids = _dedupe(self.plan_market_ids)
        self.execution_market_ids = _dedupe(self.execution_market_ids)
        self.legging_risk_reasons = _dedupe(self.legging_risk_reasons)
        self.legs = [leg.model_copy() for leg in self.legs]
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        return self


class MultiVenuePaperSurface(BaseModel):
    schema_version: str = "v1"
    report_id: str | None = None
    source_report_id: str | None = None
    market_count: int = 0
    plan_count: int = 0
    tradeable_plan_count: int = 0
    manual_review_plan_count: int = 0
    simulated_plan_count: int = 0
    skipped_plan_count: int = 0
    leg_count: int = 0
    covered_leg_count: int = 0
    missing_snapshot_leg_count: int = 0
    legging_risk_count: int = 0
    rejected_leg_rate: float = 0.0
    execution_routes: dict[str, int] = Field(default_factory=dict)
    paper_status_counts: dict[str, int] = Field(default_factory=dict)
    total_requested_notional_usd: float = 0.0
    total_allocated_notional_usd: float = 0.0
    total_simulated_notional_usd: float = 0.0
    total_requested_quantity: float = 0.0
    total_filled_quantity: float = 0.0
    total_fees_usd: float = 0.0
    gross_pnl_usd: float = 0.0
    net_pnl_usd: float = 0.0
    fill_rate: float = 0.0
    partial_fill_rate: float = 0.0
    no_trade_leg_count: int = 0
    no_trade_leg_rate: float = 0.0
    stale_block_count: int = 0
    stale_block_rate: float = 0.0
    hedge_completion_rate: float = 0.0
    legging_loss_usd: float = 0.0
    average_slippage_bps: float = 0.0
    spread_mean_bps: float | None = None
    max_abs_slippage_bps: float = 0.0
    legging_risk_plan_ids: list[str] = Field(default_factory=list)
    comparison_only_plan_count: int = 0
    relative_value_plan_count: int = 0
    cross_venue_signal_plan_count: int = 0
    true_arbitrage_plan_count: int = 0
    execution_filter_reason_codes: list[str] = Field(default_factory=list)
    execution_filter_reason_code_counts: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MultiVenuePaperReport(BaseModel):
    schema_version: str = "v1"
    report_id: str = Field(default_factory=lambda: f"mvprpt_{uuid4().hex[:12]}")
    source_report_id: str | None = None
    market_count: int = 0
    plan_results: list[MultiVenuePaperPlanResult] = Field(default_factory=list)
    surface: MultiVenuePaperSurface = Field(default_factory=MultiVenuePaperSurface)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "MultiVenuePaperReport":
        self.plan_results = [plan.model_copy() for plan in self.plan_results]
        self.market_count = max(0, int(self.market_count))
        self.surface = self._build_surface()
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        return self

    @property
    def plan_count(self) -> int:
        return self.surface.plan_count

    @property
    def tradeable_plan_count(self) -> int:
        return self.surface.tradeable_plan_count

    @property
    def manual_review_plan_count(self) -> int:
        return self.surface.manual_review_plan_count

    @property
    def legging_risk_count(self) -> int:
        return self.surface.legging_risk_count

    @property
    def total_fees_usd(self) -> float:
        return self.surface.total_fees_usd

    @property
    def gross_pnl_usd(self) -> float:
        return self.surface.gross_pnl_usd

    @property
    def net_pnl_usd(self) -> float:
        return self.surface.net_pnl_usd

    @property
    def average_slippage_bps(self) -> float:
        return self.surface.average_slippage_bps

    @property
    def max_abs_slippage_bps(self) -> float:
        return self.surface.max_abs_slippage_bps

    @property
    def fill_rate(self) -> float:
        return self.surface.fill_rate

    @property
    def partial_fill_rate(self) -> float:
        return self.surface.partial_fill_rate

    @property
    def no_trade_leg_count(self) -> int:
        return self.surface.no_trade_leg_count

    @property
    def no_trade_leg_rate(self) -> float:
        return self.surface.no_trade_leg_rate

    @property
    def stale_block_rate(self) -> float:
        return self.surface.stale_block_rate

    @property
    def hedge_completion_rate(self) -> float:
        return self.surface.hedge_completion_rate

    @property
    def legging_loss_usd(self) -> float:
        return self.surface.legging_loss_usd

    def _build_surface(self) -> MultiVenuePaperSurface:
        execution_routes: dict[str, int] = {}
        paper_status_counts: dict[str, int] = {}
        legging_risk_plan_ids: list[str] = []
        comparison_only_plan_count = 0
        relative_value_plan_count = 0
        cross_venue_signal_plan_count = 0
        true_arbitrage_plan_count = 0
        execution_filter_reason_codes: list[str] = []
        execution_filter_reason_code_counts: dict[str, int] = {}
        total_requested_notional_usd = 0.0
        total_allocated_notional_usd = 0.0
        total_simulated_notional_usd = 0.0
        total_requested_quantity = 0.0
        total_filled_quantity = 0.0
        total_fees_usd = 0.0
        gross_pnl_usd = 0.0
        net_pnl_usd = 0.0
        legging_loss_usd = 0.0
        average_slippage_weight = 0.0
        average_slippage_weight_denominator = 0.0
        spread_weight = 0.0
        spread_weight_denominator = 0.0
        max_abs_slippage_bps = 0.0
        covered_leg_count = 0
        missing_snapshot_leg_count = 0
        leg_count = 0
        partial_leg_count = 0
        rejected_leg_count = 0
        no_trade_leg_count = 0
        stale_block_count = 0
        legging_risk_count = 0
        tradeable_plan_count = 0
        manual_review_plan_count = 0
        simulated_plan_count = 0
        skipped_plan_count = 0
        hedge_completion_rate_total = 0.0
        hedge_completion_rate_count = 0
        for plan in self.plan_results:
            execution_routes[plan.route] = execution_routes.get(plan.route, 0) + 1
            if plan.taxonomy == CrossVenueTaxonomy.comparison_only:
                comparison_only_plan_count += 1
            elif plan.taxonomy == CrossVenueTaxonomy.relative_value:
                relative_value_plan_count += 1
            elif plan.taxonomy == CrossVenueTaxonomy.cross_venue_signal:
                cross_venue_signal_plan_count += 1
            elif plan.taxonomy == CrossVenueTaxonomy.true_arbitrage:
                true_arbitrage_plan_count += 1
            execution_filter_reason_codes.extend(plan.execution_filter_reason_codes)
            for reason_code in plan.execution_filter_reason_codes:
                execution_filter_reason_code_counts[reason_code] = execution_filter_reason_code_counts.get(reason_code, 0) + 1
            total_requested_notional_usd += float(plan.requested_notional_usd)
            total_allocated_notional_usd += float(plan.allocated_notional_usd)
            total_simulated_notional_usd += float(plan.simulated_notional_usd)
            total_fees_usd += float(plan.fee_paid_usd)
            gross_pnl_usd += float(plan.gross_pnl_usd)
            net_pnl_usd += float(plan.net_pnl_usd)
            legging_loss_usd += float(plan.legging_loss_usd)
            tradeable_plan_count += int(bool(plan.tradeable))
            manual_review_plan_count += int(bool(plan.manual_review_required))
            simulated_plan_count += int(bool(plan.paper_simulated))
            skipped_plan_count += int(not plan.paper_simulated)
            if plan.has_arb_plan:
                hedge_completion_rate_total += float(plan.hedge_completion_rate)
                hedge_completion_rate_count += 1
            if plan.legging_risk:
                legging_risk_count += 1
                legging_risk_plan_ids.append(plan.execution_plan_id)
            for leg in plan.legs:
                leg_count += 1
                if leg.paper_trade is not None:
                    total_requested_quantity += float(leg.paper_trade.requested_quantity)
                    total_filled_quantity += float(leg.paper_trade.filled_quantity)
                if leg.spread_bps is not None and leg.allocated_notional_usd > 0:
                    spread_weight += abs(float(leg.spread_bps)) * float(leg.allocated_notional_usd)
                    spread_weight_denominator += float(leg.allocated_notional_usd)
                if leg.snapshot_available:
                    covered_leg_count += 1
                else:
                    missing_snapshot_leg_count += 1
                if leg.stale_blocked:
                    stale_block_count += 1
                if leg.paper_trade is not None and leg.paper_trade.postmortem().no_trade_zone:
                    no_trade_leg_count += 1
                if leg.paper_trade_status is PaperTradeStatus.partial:
                    partial_leg_count += 1
                if leg.paper_trade_status is PaperTradeStatus.rejected:
                    rejected_leg_count += 1
                paper_status_counts[leg.paper_trade_status.value] = paper_status_counts.get(leg.paper_trade_status.value, 0) + 1
                if leg.allocated_notional_usd > 0:
                    average_slippage_weight += abs(float(leg.slippage_bps)) * float(leg.allocated_notional_usd)
                    average_slippage_weight_denominator += float(leg.allocated_notional_usd)
                max_abs_slippage_bps = max(max_abs_slippage_bps, abs(float(leg.slippage_bps)))
        average_slippage_bps = 0.0 if average_slippage_weight_denominator <= 0.0 else round(average_slippage_weight / average_slippage_weight_denominator, 2)
        spread_mean_bps = None if spread_weight_denominator <= 0.0 else round(spread_weight / spread_weight_denominator, 2)
        fill_rate = 0.0 if total_requested_quantity <= 0.0 else round(total_filled_quantity / total_requested_quantity, 6)
        partial_fill_rate = 0.0 if covered_leg_count <= 0 else round(partial_leg_count / covered_leg_count, 6)
        no_trade_leg_rate = 0.0 if leg_count <= 0 else round(no_trade_leg_count / leg_count, 6)
        stale_block_rate = 0.0 if leg_count <= 0 else round(stale_block_count / leg_count, 6)
        hedge_completion_rate = 0.0 if hedge_completion_rate_count <= 0 else round(hedge_completion_rate_total / hedge_completion_rate_count, 6)
        rejected_leg_rate = 0.0 if leg_count <= 0 else round(rejected_leg_count / leg_count, 6)
        return MultiVenuePaperSurface(
            report_id=self.report_id,
            source_report_id=self.source_report_id,
            market_count=self.market_count,
            plan_count=len(self.plan_results),
            tradeable_plan_count=tradeable_plan_count,
            manual_review_plan_count=manual_review_plan_count,
            simulated_plan_count=simulated_plan_count,
            skipped_plan_count=skipped_plan_count,
            leg_count=leg_count,
            covered_leg_count=covered_leg_count,
            missing_snapshot_leg_count=missing_snapshot_leg_count,
            stale_block_count=stale_block_count,
            legging_risk_count=legging_risk_count,
            rejected_leg_rate=rejected_leg_rate,
            execution_routes={key: value for key, value in sorted(execution_routes.items())},
            paper_status_counts={key: value for key, value in sorted(paper_status_counts.items())},
            total_requested_notional_usd=round(total_requested_notional_usd, 6),
            total_allocated_notional_usd=round(total_allocated_notional_usd, 6),
            total_simulated_notional_usd=round(total_simulated_notional_usd, 6),
            total_requested_quantity=round(total_requested_quantity, 6),
            total_filled_quantity=round(total_filled_quantity, 6),
            total_fees_usd=round(total_fees_usd, 6),
            gross_pnl_usd=round(gross_pnl_usd, 6),
            net_pnl_usd=round(net_pnl_usd, 6),
            fill_rate=fill_rate,
            partial_fill_rate=partial_fill_rate,
            no_trade_leg_count=no_trade_leg_count,
            no_trade_leg_rate=no_trade_leg_rate,
            stale_block_rate=stale_block_rate,
            hedge_completion_rate=hedge_completion_rate,
            legging_loss_usd=round(legging_loss_usd, 6),
            average_slippage_bps=average_slippage_bps,
            spread_mean_bps=spread_mean_bps,
            max_abs_slippage_bps=round(max_abs_slippage_bps, 2),
            legging_risk_plan_ids=_dedupe(legging_risk_plan_ids),
            comparison_only_plan_count=comparison_only_plan_count,
            relative_value_plan_count=relative_value_plan_count,
            cross_venue_signal_plan_count=cross_venue_signal_plan_count,
            true_arbitrage_plan_count=true_arbitrage_plan_count,
            execution_filter_reason_codes=_dedupe(execution_filter_reason_codes),
            execution_filter_reason_code_counts={key: value for key, value in sorted(execution_filter_reason_code_counts.items())},
            metadata={
                "paper_plan_count": len(self.plan_results),
                "paper_status_counts": {key: value for key, value in sorted(paper_status_counts.items())},
                "fill_rate": fill_rate,
                "partial_fill_rate": partial_fill_rate,
                "no_trade_leg_count": no_trade_leg_count,
                "no_trade_leg_rate": no_trade_leg_rate,
                "stale_block_count": stale_block_count,
                "stale_block_rate": stale_block_rate,
                "hedge_completion_rate": hedge_completion_rate,
                "legging_loss_usd": round(legging_loss_usd, 6),
                "comparison_only_plan_count": comparison_only_plan_count,
                "relative_value_plan_count": relative_value_plan_count,
                "cross_venue_signal_plan_count": cross_venue_signal_plan_count,
                "true_arbitrage_plan_count": true_arbitrage_plan_count,
                "execution_filter_reason_codes": _dedupe(execution_filter_reason_codes),
                "execution_filter_reason_code_counts": {key: value for key, value in sorted(execution_filter_reason_code_counts.items())},
            },
        )

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "MultiVenuePaperReport":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


@dataclass
class MultiVenuePaperSimulator:
    paper_simulator: PaperTradeSimulator = field(default_factory=PaperTradeSimulator)
    default_target_notional_usd: float = 1000.0

    def simulate_report(
        self,
        execution_report: MultiVenueExecutionReport,
        *,
        markets: Sequence[MarketDescriptor] | None = None,
        snapshots: dict[str, MarketSnapshot] | None = None,
        target_notional_usd: float | None = None,
    ) -> MultiVenuePaperReport:
        market_lookup = {market.market_id: market for market in (markets or [])}
        snapshot_lookup = dict(snapshots or {})
        plan_results: list[MultiVenuePaperPlanResult] = []
        for plan in execution_report.plans:
            plan_results.append(
                self._simulate_plan(
                    plan,
                    market_lookup=market_lookup,
                    snapshot_lookup=snapshot_lookup,
                    target_notional_usd=target_notional_usd,
                )
            )
        return MultiVenuePaperReport(
            source_report_id=execution_report.report_id,
            market_count=execution_report.market_count,
            plan_results=plan_results,
            metadata={
                "execution_report_id": execution_report.report_id,
                "cross_venue_report_id": execution_report.cross_venue_report.report_id,
                "paper_simulator_fee_bps": self.paper_simulator.fee_bps,
                "paper_simulator_max_slippage_bps": self.paper_simulator.max_slippage_bps,
            },
        )

    def _simulate_plan(
        self,
        plan: MultiVenueExecutionPlan,
        *,
        market_lookup: dict[str, MarketDescriptor],
        snapshot_lookup: dict[str, MarketSnapshot],
        target_notional_usd: float | None = None,
    ) -> MultiVenuePaperPlanResult:
        legs = self._plan_legs(
            plan,
            market_lookup=market_lookup,
            target_notional_usd=target_notional_usd,
        )
        leg_results: list[MultiVenuePaperLegResult] = []
        gross_pnl_usd = 0.0
        fee_paid_usd = 0.0
        net_pnl_usd = 0.0
        average_slippage_weight = 0.0
        average_slippage_weight_denominator = 0.0
        max_abs_slippage_bps = 0.0
        simulated_notional_usd = 0.0
        legging_risk_reasons: list[str] = []
        total_requested_quantity = 0.0
        total_filled_quantity = 0.0
        stale_block_count = 0
        no_trade_leg_count = 0
        for leg in legs:
            snapshot = snapshot_lookup.get(leg.market_ref)
            leg_result = self._simulate_leg(plan, leg, snapshot)
            leg_results.append(leg_result)
            if leg_result.snapshot_available and leg_result.paper_trade is not None:
                simulated_notional_usd += float(leg_result.allocated_notional_usd)
                total_requested_quantity += float(leg_result.paper_trade.requested_quantity)
                total_filled_quantity += float(leg_result.paper_trade.filled_quantity)
            if leg_result.stale_blocked:
                stale_block_count += 1
            if leg_result.paper_trade is not None and leg_result.paper_trade.postmortem().no_trade_zone:
                no_trade_leg_count += 1
            gross_pnl_usd += float(leg_result.gross_pnl_usd)
            fee_paid_usd += float(leg_result.fee_paid_usd)
            net_pnl_usd += float(leg_result.net_pnl_usd)
            if leg_result.allocated_notional_usd > 0:
                average_slippage_weight += abs(float(leg_result.slippage_bps)) * float(leg_result.allocated_notional_usd)
                average_slippage_weight_denominator += float(leg_result.allocated_notional_usd)
            max_abs_slippage_bps = max(max_abs_slippage_bps, abs(float(leg_result.slippage_bps)))
            if leg_result.legging_risk:
                legging_risk_reasons.extend(leg_result.legging_risk_reasons)

        simulated_leg_count = sum(1 for leg in leg_results if leg.snapshot_available)
        skipped_leg_count = sum(1 for leg in leg_results if leg.paper_trade_status is PaperTradeStatus.skipped)
        filled_leg_count = sum(1 for leg in leg_results if leg.paper_trade_status is PaperTradeStatus.filled)
        partial_leg_count = sum(1 for leg in leg_results if leg.paper_trade_status is PaperTradeStatus.partial)
        rejected_leg_count = sum(1 for leg in leg_results if leg.paper_trade_status is PaperTradeStatus.rejected)
        snapshot_coverage = 0.0 if not leg_results else round(simulated_leg_count / len(leg_results), 6)
        legging_risk = self._legging_risk(plan, leg_results)
        if legging_risk:
            legging_risk_reasons = _dedupe([
                *(legging_risk_reasons or []),
                *self._legging_risk_reasons(plan, leg_results),
            ])
        requested_notional_usd = sum(float(getattr(leg, "notional_usd", 0.0)) for leg in legs)
        allocated_notional_usd = sum(float(leg.allocated_notional_usd) for leg in leg_results)
        fill_rate = 0.0 if total_requested_quantity <= 0.0 else round(total_filled_quantity / total_requested_quantity, 6)
        partial_fill_rate = 0.0 if simulated_leg_count <= 0 else round(partial_leg_count / simulated_leg_count, 6)
        no_trade_leg_rate = 0.0 if len(leg_results) <= 0 else round(no_trade_leg_count / len(leg_results), 6)
        stale_block_rate = 0.0 if len(leg_results) <= 0 else round(stale_block_count / len(leg_results), 6)
        hedge_completion_rate = round(float(plan.arb_plan.hedge_completion_ratio), 6) if plan.arb_plan is not None else 0.0
        legging_loss_usd = round(max(0.0, -net_pnl_usd) if legging_risk else 0.0, 6)
        average_slippage_bps = 0.0 if average_slippage_weight_denominator <= 0.0 else round(average_slippage_weight / average_slippage_weight_denominator, 2)
        spread_weight = 0.0
        spread_weight_denominator = 0.0
        for leg_result in leg_results:
            if leg_result.spread_bps is not None and leg_result.allocated_notional_usd > 0:
                spread_weight += abs(float(leg_result.spread_bps)) * float(leg_result.allocated_notional_usd)
                spread_weight_denominator += float(leg_result.allocated_notional_usd)
        spread_mean_bps = None if spread_weight_denominator <= 0.0 else round(spread_weight / spread_weight_denominator, 2)
        rejected_leg_rate = 0.0 if len(leg_results) <= 0 else round(rejected_leg_count / len(leg_results), 6)
        return MultiVenuePaperPlanResult(
            execution_plan_id=plan.execution_plan_id,
            candidate_id=plan.candidate_id,
            comparison_id=plan.comparison_id,
            canonical_event_id=plan.canonical_event_id,
            route=plan.route,
            tradeable=plan.tradeable,
            manual_review_required=plan.manual_review_required,
            taxonomy=plan.taxonomy,
            execution_filter_reason_codes=list(plan.execution_filter_reason_codes),
            plan_market_ids=list(plan.market_ids),
            execution_market_ids=list(plan.execution_market_ids),
            requested_notional_usd=requested_notional_usd,
            allocated_notional_usd=allocated_notional_usd,
            simulated_notional_usd=round(simulated_notional_usd, 6),
            paper_simulated=simulated_leg_count > 0,
            snapshot_coverage=snapshot_coverage,
            simulated_leg_count=simulated_leg_count,
            skipped_leg_count=skipped_leg_count,
            filled_leg_count=filled_leg_count,
            partial_leg_count=partial_leg_count,
            rejected_leg_count=rejected_leg_count,
            gross_pnl_usd=round(gross_pnl_usd, 6),
            fee_paid_usd=round(fee_paid_usd, 6),
            net_pnl_usd=round(net_pnl_usd, 6),
            fill_rate=fill_rate,
            partial_fill_rate=partial_fill_rate,
            no_trade_leg_count=no_trade_leg_count,
            no_trade_leg_rate=no_trade_leg_rate,
            stale_block_count=stale_block_count,
            stale_block_rate=stale_block_rate,
            hedge_completion_rate=hedge_completion_rate,
            has_arb_plan=bool(plan.arb_plan is not None),
            legging_loss_usd=legging_loss_usd,
            average_slippage_bps=average_slippage_bps,
            max_abs_slippage_bps=round(max_abs_slippage_bps, 2),
            legging_risk=legging_risk,
            legging_risk_reasons=legging_risk_reasons,
            legs=leg_results,
            metadata={
                "paper_trade_count": len([leg for leg in leg_results if leg.paper_trade is not None]),
                "snapshot_coverage": snapshot_coverage,
                "filled_leg_count": filled_leg_count,
                "partial_leg_count": partial_leg_count,
                "skipped_leg_count": skipped_leg_count,
                "stale_block_count": stale_block_count,
                "rejected_leg_rate": rejected_leg_rate,
                "fill_rate": fill_rate,
                "partial_fill_rate": partial_fill_rate,
                "hedge_completion_rate": hedge_completion_rate,
                "has_arb_plan": bool(plan.arb_plan is not None),
                "legging_loss_usd": legging_loss_usd,
                "spread_mean_bps": spread_mean_bps,
            },
        )

    def _plan_legs(
        self,
        plan: MultiVenueExecutionPlan,
        *,
        market_lookup: dict[str, MarketDescriptor],
        target_notional_usd: float | None = None,
    ) -> list[ArbPlanLeg]:
        if plan.arb_plan is not None and plan.arb_plan.legs:
            return [leg.model_copy() for leg in plan.arb_plan.legs]
        market_ids = list(plan.execution_market_ids or plan.market_ids or plan.read_only_market_ids)
        if not market_ids:
            return []
        total_notional = float(target_notional_usd if target_notional_usd is not None else self.default_target_notional_usd)
        per_leg = 0.0 if not market_ids else total_notional / len(market_ids)
        legs: list[ArbPlanLeg] = []
        for market_id in market_ids:
            market = market_lookup.get(market_id)
            legs.append(
                ArbPlanLeg(
                    market_ref=market_id,
                    venue=market.venue if market is not None else VenueName.custom,
                    side=TradeSide.buy,
                    position_side=TradeSide.yes,
                    notional_usd=per_leg,
                    rationale="synthetic_multi_venue_paper_leg",
                )
            )
        return legs

    def _simulate_leg(
        self,
        plan: MultiVenueExecutionPlan,
        leg: ArbPlanLeg,
        snapshot: MarketSnapshot | None,
    ) -> MultiVenuePaperLegResult:
        allocated_notional_usd = max(0.0, float(leg.notional_usd))
        if snapshot is None:
            paper_trade = PaperTradeSimulation(
                run_id=f"{plan.execution_plan_id}:{leg.leg_id}",
                market_id=leg.market_ref,
                venue=leg.venue,
                action=DecisionAction.bet,
                position_side=leg.position_side or TradeSide.yes,
                execution_side=leg.side,
                stake=allocated_notional_usd,
                requested_quantity=0.0,
                filled_quantity=0.0,
                average_fill_price=None,
                reference_price=None,
                gross_notional=0.0,
                fee_paid=0.0,
                cash_flow=0.0,
                slippage_bps=0.0,
                status=PaperTradeStatus.skipped,
                snapshot_id=None,
                fills=[],
                metadata={
                    "reason": "snapshot_missing",
                    "paper_mode": "multi_venue_preview",
                    "manual_review_required": plan.manual_review_required,
                    "plan_tradeable": plan.tradeable,
                    "no_trade_zone": True,
                },
            )
            return MultiVenuePaperLegResult(
                plan_id=plan.execution_plan_id,
                candidate_id=plan.candidate_id,
                comparison_id=plan.comparison_id,
                canonical_event_id=plan.canonical_event_id,
                leg_id=leg.leg_id,
                market_id=leg.market_ref,
                venue=leg.venue,
                execution_side=leg.side,
                position_side=leg.position_side or TradeSide.yes,
                requested_notional_usd=allocated_notional_usd,
                allocated_notional_usd=allocated_notional_usd,
                snapshot_available=False,
                paper_trade=paper_trade,
                paper_trade_status=paper_trade.status,
                mark_price=None,
                spread_bps=None,
                gross_pnl_usd=0.0,
                fee_paid_usd=0.0,
                net_pnl_usd=0.0,
                fill_rate=0.0,
                partial_fill_rate=0.0,
                slippage_bps=0.0,
                legging_risk=True,
                legging_risk_reasons=["snapshot_missing"],
                stale_blocked=False,
                notes=["snapshot_missing"],
                metadata={
                    "paper_mode": "multi_venue_preview",
                    "manual_review_required": plan.manual_review_required,
                    "plan_tradeable": plan.tradeable,
                    "no_trade_zone": True,
                },
            )
        paper_trade = self.paper_simulator.simulate(
            snapshot,
            position_side=leg.position_side or TradeSide.yes,
            execution_side=leg.side,
            stake=allocated_notional_usd,
            run_id=f"{plan.execution_plan_id}:{leg.leg_id}",
            market_id=leg.market_ref,
            venue=leg.venue,
            limit_price=leg.limit_price,
            action=DecisionAction.bet,
            metadata={
                "paper_mode": "multi_venue_preview",
                "plan_id": plan.execution_plan_id,
                "candidate_id": plan.candidate_id,
                "comparison_id": plan.comparison_id,
                "manual_review_required": plan.manual_review_required,
                "plan_tradeable": plan.tradeable,
            },
        )
        paper_postmortem = paper_trade.postmortem()
        mark_price = snapshot.market_implied_probability or snapshot.midpoint_yes or paper_trade.average_fill_price or paper_trade.reference_price
        gross_pnl = _mark_to_market_pnl(paper_trade, mark_price)
        fee_paid = float(paper_trade.fee_paid)
        net_pnl = round(gross_pnl - fee_paid, 6)
        legging_risk_reasons: list[str] = []
        if paper_postmortem.no_trade_zone:
            legging_risk_reasons.append("no_trade_zone")
        if paper_trade.status is PaperTradeStatus.partial:
            legging_risk_reasons.append("partial_fill")
        if paper_trade.status is PaperTradeStatus.rejected:
            legging_risk_reasons.append("rejected")
        if plan.arb_plan is not None and plan.arb_plan.max_unhedged_leg_ms > 0:
            legging_risk_reasons.append(f"unhedged_leg_window:{plan.arb_plan.max_unhedged_leg_ms}")
        stale_blocked = bool(paper_postmortem.stale_blocked)
        if stale_blocked:
            legging_risk_reasons.append("snapshot_stale")
        if paper_trade.metadata.get("slippage_guard_triggered"):
            legging_risk_reasons.append("slippage_guard_triggered")
        if paper_postmortem.recommendation != "hold":
            legging_risk_reasons.append(f"paper_recommendation:{paper_postmortem.recommendation}")
        if paper_postmortem.no_trade_zone and paper_trade.status in {PaperTradeStatus.filled, PaperTradeStatus.partial}:
            legging_risk_reasons.append("reclassified_no_trade")
        return MultiVenuePaperLegResult(
            plan_id=plan.execution_plan_id,
            candidate_id=plan.candidate_id,
            comparison_id=plan.comparison_id,
            canonical_event_id=plan.canonical_event_id,
            leg_id=leg.leg_id,
            market_id=leg.market_ref,
            venue=leg.venue,
            execution_side=leg.side,
            position_side=leg.position_side or TradeSide.yes,
            requested_notional_usd=allocated_notional_usd,
            allocated_notional_usd=allocated_notional_usd,
            snapshot_id=snapshot.snapshot_id,
            snapshot_available=True,
            paper_trade=paper_trade,
            paper_trade_status=paper_trade.status,
            mark_price=mark_price,
            spread_bps=snapshot.spread_bps,
            gross_pnl_usd=round(gross_pnl, 6),
            fee_paid_usd=round(fee_paid, 6),
            net_pnl_usd=net_pnl,
            fill_rate=float(paper_trade.postmortem().fill_rate),
            partial_fill_rate=1.0 if paper_trade.status is PaperTradeStatus.partial else 0.0,
            slippage_bps=float(paper_trade.slippage_bps),
            legging_risk=bool(legging_risk_reasons),
            legging_risk_reasons=_dedupe(legging_risk_reasons),
            stale_blocked=stale_blocked,
            notes=[paper_trade.status.value, *paper_postmortem.notes],
            metadata={
                "paper_mode": "multi_venue_preview",
                "fee_bps": paper_trade.metadata.get("fee_bps"),
                "manual_review_required": plan.manual_review_required,
                "plan_tradeable": plan.tradeable,
                "stale_blocked": stale_blocked,
                "no_trade_zone": bool(paper_postmortem.no_trade_zone),
                "paper_trade_reclassified_no_trade": bool(
                    paper_postmortem.no_trade_zone and paper_trade.status in {PaperTradeStatus.filled, PaperTradeStatus.partial}
                ),
                "paper_trade_postmortem": paper_postmortem.model_dump(mode="json"),
                "paper_trade_recommendation": paper_postmortem.recommendation,
            },
        )

    def _legging_risk(self, plan: MultiVenueExecutionPlan, leg_results: list[MultiVenuePaperLegResult]) -> bool:
        if len(leg_results) <= 1:
            return False
        if any(not leg.snapshot_available for leg in leg_results):
            return True
        if any(leg.stale_blocked for leg in leg_results):
            return True
        if any(leg.paper_trade is not None and leg.paper_trade.postmortem().no_trade_zone for leg in leg_results):
            return True
        if any(leg.paper_trade_status in {PaperTradeStatus.partial, PaperTradeStatus.rejected} for leg in leg_results):
            return True
        if plan.arb_plan is not None and plan.arb_plan.max_unhedged_leg_ms > 0:
            return True
        return False

    def _legging_risk_reasons(self, plan: MultiVenueExecutionPlan, leg_results: list[MultiVenuePaperLegResult]) -> list[str]:
        reasons: list[str] = []
        if any(not leg.snapshot_available for leg in leg_results):
            reasons.append("snapshot_missing")
        if any(leg.stale_blocked for leg in leg_results):
            reasons.append("snapshot_stale")
        if any(leg.paper_trade is not None and leg.paper_trade.postmortem().no_trade_zone for leg in leg_results):
            reasons.append("no_trade_zone")
        if any(leg.paper_trade_status is PaperTradeStatus.partial for leg in leg_results):
            reasons.append("partial_fill")
        if any(leg.paper_trade_status is PaperTradeStatus.rejected for leg in leg_results):
            reasons.append("rejected_fill")
        if any(leg.paper_trade is not None and leg.paper_trade.metadata.get("slippage_guard_triggered") for leg in leg_results):
            reasons.append("slippage_guard_triggered")
        if plan.arb_plan is not None and plan.arb_plan.max_unhedged_leg_ms > 0:
            reasons.append(f"unhedged_leg_window:{plan.arb_plan.max_unhedged_leg_ms}")
        if plan.manual_review_required:
            reasons.append("manual_review_required")
        return _dedupe(reasons)


def build_multi_venue_paper_report(
    markets: Sequence[MarketDescriptor] | None = None,
    *,
    execution_report: MultiVenueExecutionReport | None = None,
    snapshots: dict[str, MarketSnapshot] | None = None,
    target_notional_usd: float | None = None,
    paper_simulator: PaperTradeSimulator | None = None,
) -> MultiVenuePaperReport:
    if execution_report is None:
        if markets is None:
            raise ValueError("markets must be provided when execution_report is omitted")
        from .multi_venue_executor import build_multi_venue_execution_report

        execution_report = build_multi_venue_execution_report(markets, snapshots=snapshots, target_notional_usd=target_notional_usd or 1000.0)
    simulator = MultiVenuePaperSimulator(
        paper_simulator=paper_simulator or PaperTradeSimulator(),
        default_target_notional_usd=target_notional_usd or 1000.0,
    )
    return simulator.simulate_report(
        execution_report,
        markets=markets,
        snapshots=snapshots,
        target_notional_usd=target_notional_usd,
    )


def _mark_to_market_pnl(paper_trade: PaperTradeSimulation, mark_price: float | None) -> float:
    if paper_trade.filled_quantity <= 0 or mark_price is None or paper_trade.average_fill_price is None:
        return 0.0
    if paper_trade.execution_side == TradeSide.buy:
        return round(paper_trade.filled_quantity * (float(mark_price) - float(paper_trade.average_fill_price)), 6)
    return round(paper_trade.filled_quantity * (float(paper_trade.average_fill_price) - float(mark_price)), 6)


def _dedupe(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(_normalized_text(item) for item in items if _normalized_text(item)))


__all__ = [
    "MultiVenuePaperLegResult",
    "MultiVenuePaperPlanResult",
    "MultiVenuePaperReport",
    "MultiVenuePaperSimulator",
    "MultiVenuePaperSurface",
    "build_multi_venue_paper_report",
]
