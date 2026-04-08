from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from .models import CrossVenueMatch, MarketDescriptor, MarketSnapshot, TradeSide, VenueName
from .registry import DEFAULT_VENUE_EXECUTION_REGISTRY
from .slippage_liquidity import SlippageLiquidityReport, SlippageLiquiditySimulator, SlippageLiquidityStatus
from .spread_monitor import (
    SpreadMonitor,
    SpreadMonitorReport,
    SpreadOpportunity,
    SpreadOpportunityClass,
    SpreadOpportunityDirection,
)


class ArbitrageVerdict(str, Enum):
    comparison_only = "comparison_only"
    signal_only = "signal_only"
    executable_candidate = "executable_candidate"


class ArbitrageTaxonomy(str, Enum):
    comparison_only = "comparison_only"
    relative_value = "relative_value"
    cross_venue_signal = "cross_venue_signal"
    true_arbitrage = "true_arbitrage"


class ArbitrageLegPlan(BaseModel):
    schema_version: str = "v1"
    leg_id: str = Field(default_factory=lambda: f"arbleg_{uuid4().hex[:12]}")
    opportunity_id: str
    market_id: str
    venue: VenueName
    position_side: TradeSide
    execution_side: TradeSide
    requested_quantity: float = 0.0
    requested_notional: float = 0.0
    filled_quantity: float = 0.0
    filled_notional: float = 0.0
    average_fill_price: float | None = None
    slippage_bps: float = 0.0
    fee_paid: float = 0.0
    fill_ratio: float = 0.0
    status: SlippageLiquidityStatus = SlippageLiquidityStatus.rejected
    snapshot_id: str | None = None
    source: str = "orderbook"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArbitragePlan(BaseModel):
    schema_version: str = "v1"
    plan_id: str = Field(default_factory=lambda: f"arbplan_{uuid4().hex[:12]}")
    opportunity_id: str
    canonical_event_id: str
    verdict: ArbitrageVerdict = ArbitrageVerdict.comparison_only
    direction: SpreadOpportunityDirection = SpreadOpportunityDirection.unknown
    spread_bps: float = 0.0
    gross_edge_bps: float = 0.0
    estimated_roundtrip_slippage_bps: float = 0.0
    estimated_fee_bps: float = 0.0
    net_edge_bps: float = 0.0
    executable: bool = False
    comparison_state: str = "comparison_only"
    narrative_risk_flags: list[str] = Field(default_factory=list)
    comparable_group_id: str | None = None
    max_unhedged_leg_ms: int = 2500
    hedge_completion_ratio: float = 0.0
    hedge_completion_ready: bool = False
    legging_risk: bool = False
    legging_risk_reasons: list[str] = Field(default_factory=list)
    taxonomy: ArbitrageTaxonomy = ArbitrageTaxonomy.comparison_only
    execution_filter_reason_codes: list[str] = Field(default_factory=list)
    buy_leg: ArbitrageLegPlan | None = None
    sell_leg: ArbitrageLegPlan | None = None
    reason_codes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArbitrageAssessment(BaseModel):
    schema_version: str = "v1"
    assessment_id: str = Field(default_factory=lambda: f"arbass_{uuid4().hex[:12]}")
    opportunity_id: str
    canonical_event_id: str
    verdict: ArbitrageVerdict = ArbitrageVerdict.comparison_only
    opportunity: SpreadOpportunity
    plan: ArbitragePlan | None = None
    execution_ready: bool = False
    comparison_state: str = "comparison_only"
    narrative_risk_flags: list[str] = Field(default_factory=list)
    hedge_completion_ratio: float = 0.0
    legging_risk: bool = False
    legging_risk_reasons: list[str] = Field(default_factory=list)
    taxonomy: ArbitrageTaxonomy = ArbitrageTaxonomy.comparison_only
    execution_filter_reason_codes: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArbitrageLabReport(BaseModel):
    schema_version: str = "v1"
    report_id: str = Field(default_factory=lambda: f"arbrpt_{uuid4().hex[:12]}")
    monitor_report: SpreadMonitorReport
    assessments: list[ArbitrageAssessment] = Field(default_factory=list)
    comparison_count: int = 0
    signal_count: int = 0
    executable_count: int = 0
    manual_review_count: int = 0
    narrative_risk_count: int = 0
    legging_risk_count: int = 0
    hedge_completion_ready_count: int = 0
    average_hedge_completion_ratio: float = 0.0
    spread_capture_rate: float = 0.0
    comparison_only_taxonomy_count: int = 0
    relative_value_taxonomy_count: int = 0
    cross_venue_signal_taxonomy_count: int = 0
    true_arbitrage_taxonomy_count: int = 0
    detected_arbitrage_count: int = 0
    invalidated_arbitrage_count: int = 0
    invalidated_arbitrage_rate: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class ArbitrageLab:
    monitor: SpreadMonitor = field(default_factory=SpreadMonitor)
    probe_quantity: float = 10.0
    min_net_edge_bps: float = 25.0
    min_fill_ratio: float = 0.95
    fee_bps: float = 0.0
    max_unhedged_leg_ms: int = 2500
    simulator: SlippageLiquiditySimulator = field(default_factory=SlippageLiquiditySimulator)

    def assess(
        self,
        markets: list[MarketDescriptor],
        *,
        snapshots: dict[str, MarketSnapshot] | None = None,
        matches: list[CrossVenueMatch] | None = None,
    ) -> ArbitrageLabReport:
        snapshots = snapshots or {}
        monitor_report = self.monitor.scan(markets, snapshots=snapshots, matches=matches)
        assessments: list[ArbitrageAssessment] = []

        for opportunity in monitor_report.opportunities:
            assessment = self._assess_opportunity(opportunity, snapshots=snapshots)
            assessments.append(assessment)

        detected_arbitrage_count = sum(
            1 for opportunity in monitor_report.opportunities if opportunity.opportunity_class == SpreadOpportunityClass.executable_candidate
        )
        invalidated_arbitrage_count = sum(
            1
            for opportunity, assessment in zip(monitor_report.opportunities, assessments)
            if opportunity.opportunity_class == SpreadOpportunityClass.executable_candidate
            and assessment.verdict != ArbitrageVerdict.executable_candidate
        )
        invalidated_arbitrage_rate = round(invalidated_arbitrage_count / max(1, detected_arbitrage_count), 6)

        return ArbitrageLabReport(
            monitor_report=monitor_report,
            assessments=assessments,
            comparison_count=sum(1 for assessment in assessments if assessment.verdict == ArbitrageVerdict.comparison_only),
            signal_count=sum(1 for assessment in assessments if assessment.verdict == ArbitrageVerdict.signal_only),
            executable_count=sum(1 for assessment in assessments if assessment.verdict == ArbitrageVerdict.executable_candidate),
            manual_review_count=sum(
                1
                for assessment in assessments
                if {"manual_review_required", "execution_like_venue", "narrative_spread_only"} & set(assessment.reason_codes)
            ),
            narrative_risk_count=sum(len(assessment.narrative_risk_flags) for assessment in assessments),
            legging_risk_count=sum(1 for assessment in assessments if assessment.legging_risk),
            hedge_completion_ready_count=sum(1 for assessment in assessments if assessment.hedge_completion_ratio >= self.min_fill_ratio),
            average_hedge_completion_ratio=round(
                sum(assessment.hedge_completion_ratio for assessment in assessments) / max(1, len(assessments)),
                6,
            ),
            spread_capture_rate=round(
                sum(1 for assessment in assessments if assessment.verdict == ArbitrageVerdict.executable_candidate)
                / max(1, len(monitor_report.opportunities)),
                6,
            ),
            comparison_only_taxonomy_count=sum(1 for assessment in assessments if assessment.taxonomy == ArbitrageTaxonomy.comparison_only),
            relative_value_taxonomy_count=sum(1 for assessment in assessments if assessment.taxonomy == ArbitrageTaxonomy.relative_value),
            cross_venue_signal_taxonomy_count=sum(1 for assessment in assessments if assessment.taxonomy == ArbitrageTaxonomy.cross_venue_signal),
            true_arbitrage_taxonomy_count=sum(1 for assessment in assessments if assessment.taxonomy == ArbitrageTaxonomy.true_arbitrage),
            detected_arbitrage_count=detected_arbitrage_count,
            invalidated_arbitrage_count=invalidated_arbitrage_count,
            invalidated_arbitrage_rate=invalidated_arbitrage_rate,
            metadata={
                "probe_quantity": self.probe_quantity,
                "min_net_edge_bps": self.min_net_edge_bps,
                "min_fill_ratio": self.min_fill_ratio,
                "fee_bps": self.fee_bps,
                "max_unhedged_leg_ms": self.max_unhedged_leg_ms,
                "taxonomy_counts": {
                    "comparison_only": sum(1 for assessment in assessments if assessment.taxonomy == ArbitrageTaxonomy.comparison_only),
                    "relative_value": sum(1 for assessment in assessments if assessment.taxonomy == ArbitrageTaxonomy.relative_value),
                    "cross_venue_signal": sum(1 for assessment in assessments if assessment.taxonomy == ArbitrageTaxonomy.cross_venue_signal),
                    "true_arbitrage": sum(1 for assessment in assessments if assessment.taxonomy == ArbitrageTaxonomy.true_arbitrage),
                },
                "spread_capture_rate": round(
                    sum(1 for assessment in assessments if assessment.verdict == ArbitrageVerdict.executable_candidate)
                    / max(1, len(monitor_report.opportunities)),
                    6,
                ),
                "detected_arbitrage_count": detected_arbitrage_count,
                "invalidated_arbitrage_count": invalidated_arbitrage_count,
                "invalidated_arbitrage_rate": invalidated_arbitrage_rate,
            },
        )

    def _assess_opportunity(
        self,
        opportunity: SpreadOpportunity,
        *,
        snapshots: dict[str, MarketSnapshot],
    ) -> ArbitrageAssessment:
        if opportunity.opportunity_class == SpreadOpportunityClass.comparison_only or opportunity.spread_bps is None:
            reason_codes = list(opportunity.reason_codes) or ["comparison_only"]
            return ArbitrageAssessment(
                opportunity_id=opportunity.opportunity_id,
                canonical_event_id=opportunity.canonical_event_id,
                verdict=ArbitrageVerdict.comparison_only,
                opportunity=opportunity,
                execution_ready=False,
                taxonomy=ArbitrageTaxonomy.comparison_only,
                execution_filter_reason_codes=_dedupe(reason_codes),
                reason_codes=reason_codes,
                comparison_state=opportunity.comparison_state.value,
                narrative_risk_flags=list(opportunity.narrative_risk_flags),
                legging_risk=bool(opportunity.narrative_risk_flags),
                legging_risk_reasons=_dedupe(list(opportunity.reason_codes) or ["comparison_only"]),
                metadata={
                    "monitor_class": opportunity.opportunity_class.value,
                    "taxonomy": ArbitrageTaxonomy.comparison_only.value,
                    "execution_filter_reason_codes": _dedupe(reason_codes),
                },
            )

        if opportunity.opportunity_class == SpreadOpportunityClass.executable_candidate and self._requires_manual_review(opportunity):
            plan = self._plan_from_opportunity(
                opportunity,
                buy_report=None,
                sell_report=None,
                executable=False,
                reason_codes=[self._manual_review_reason_code(opportunity)],
            )
            plan.taxonomy = ArbitrageTaxonomy.cross_venue_signal
            plan.execution_filter_reason_codes = _dedupe(list(plan.reason_codes) + list(plan.legging_risk_reasons))
            plan.metadata["taxonomy"] = plan.taxonomy.value
            plan.metadata["execution_filter_reason_codes"] = list(plan.execution_filter_reason_codes)
            execution_filter_reason_codes = self._execution_filter_reason_codes(
                opportunity,
                reason_codes=list(plan.reason_codes),
                legging_risk_reasons=list(plan.legging_risk_reasons),
                execution_ready=False,
            )
            return ArbitrageAssessment(
                opportunity_id=opportunity.opportunity_id,
                canonical_event_id=opportunity.canonical_event_id,
                verdict=ArbitrageVerdict.signal_only,
                opportunity=opportunity,
                plan=plan,
                execution_ready=False,
                taxonomy=ArbitrageTaxonomy.cross_venue_signal,
                execution_filter_reason_codes=execution_filter_reason_codes,
                reason_codes=list(plan.reason_codes),
                comparison_state="manual_review",
                narrative_risk_flags=list(opportunity.narrative_risk_flags),
                hedge_completion_ratio=plan.hedge_completion_ratio,
                legging_risk=True,
                legging_risk_reasons=_dedupe([*plan.reason_codes, *plan.legging_risk_reasons]),
                metadata={
                    "monitor_class": opportunity.opportunity_class.value,
                    "manual_review_forced": True,
                    "taxonomy": plan.taxonomy.value,
                    "execution_filter_reason_codes": list(plan.execution_filter_reason_codes),
                },
            )

        buy_market_id = opportunity.preferred_buy_market_id
        sell_market_id = opportunity.preferred_sell_market_id
        buy_snapshot = snapshots.get(buy_market_id or "")
        sell_snapshot = snapshots.get(sell_market_id or "")
        if buy_market_id is None or sell_market_id is None or buy_snapshot is None or sell_snapshot is None:
            plan = self._plan_from_opportunity(
                opportunity,
                buy_report=None,
                sell_report=None,
                executable=False,
                reason_codes=["missing_snapshot"],
            )
            plan.taxonomy = ArbitrageTaxonomy.relative_value
            plan.execution_filter_reason_codes = _dedupe(list(plan.reason_codes) + list(plan.legging_risk_reasons))
            plan.metadata["taxonomy"] = plan.taxonomy.value
            plan.metadata["execution_filter_reason_codes"] = list(plan.execution_filter_reason_codes)
            execution_filter_reason_codes = self._execution_filter_reason_codes(
                opportunity,
                reason_codes=list(plan.reason_codes),
                legging_risk_reasons=list(plan.legging_risk_reasons),
                execution_ready=False,
            )
            return ArbitrageAssessment(
                opportunity_id=opportunity.opportunity_id,
                canonical_event_id=opportunity.canonical_event_id,
                verdict=ArbitrageVerdict.signal_only,
                opportunity=opportunity,
                plan=plan,
                execution_ready=False,
                taxonomy=ArbitrageTaxonomy.relative_value,
                execution_filter_reason_codes=execution_filter_reason_codes,
                reason_codes=["missing_snapshot"],
                comparison_state=opportunity.comparison_state.value,
                narrative_risk_flags=list(opportunity.narrative_risk_flags),
                hedge_completion_ratio=plan.hedge_completion_ratio,
                legging_risk=True,
                legging_risk_reasons=_dedupe([*plan.reason_codes, *plan.legging_risk_reasons, "missing_snapshot"]),
                metadata={
                    "monitor_class": opportunity.opportunity_class.value,
                    "taxonomy": plan.taxonomy.value,
                    "execution_filter_reason_codes": list(plan.execution_filter_reason_codes),
                },
            )

        simulator = SlippageLiquiditySimulator(fee_bps=self.fee_bps)
        buy_report = opportunity.buy_fill_report or simulator.simulate(
            buy_snapshot,
            position_side=TradeSide.yes,
            execution_side=TradeSide.buy,
            requested_quantity=self.probe_quantity,
            run_id=f"arb_{uuid4().hex[:12]}",
            market_id=buy_market_id,
        )
        sell_report = opportunity.sell_fill_report or simulator.simulate(
            sell_snapshot,
            position_side=TradeSide.yes,
            execution_side=TradeSide.sell,
            requested_quantity=self.probe_quantity,
            run_id=f"arb_{uuid4().hex[:12]}",
            market_id=sell_market_id,
        )

        plan = self._plan_from_opportunity(
            opportunity,
            buy_report=buy_report,
            sell_report=sell_report,
            executable=False,
        )
        net_edge_bps = plan.net_edge_bps
        hedge_completion_ratio = round(min(buy_report.fill_ratio, sell_report.fill_ratio), 6)
        legging_risk_reasons = self._legging_risk_reasons(
            opportunity,
            buy_report=buy_report,
            sell_report=sell_report,
            hedge_completion_ratio=hedge_completion_ratio,
        )
        execution_ready = (
            opportunity.opportunity_class == SpreadOpportunityClass.executable_candidate
            and buy_report.fill_ratio >= self.min_fill_ratio
            and sell_report.fill_ratio >= self.min_fill_ratio
            and buy_report.status == SlippageLiquidityStatus.filled
            and sell_report.status == SlippageLiquidityStatus.filled
            and net_edge_bps >= self.min_net_edge_bps
        )
        plan.executable = execution_ready
        plan.verdict = ArbitrageVerdict.executable_candidate if execution_ready else ArbitrageVerdict.signal_only
        plan.hedge_completion_ratio = hedge_completion_ratio
        plan.hedge_completion_ready = execution_ready
        plan.max_unhedged_leg_ms = self.max_unhedged_leg_ms
        plan.legging_risk = bool(legging_risk_reasons)
        plan.legging_risk_reasons = _dedupe([*plan.legging_risk_reasons, *legging_risk_reasons])
        plan.reason_codes = _dedupe(list(opportunity.reason_codes) + list(plan.reason_codes) + list(plan.legging_risk_reasons))
        plan.comparison_state = opportunity.comparison_state.value
        plan.narrative_risk_flags = list(opportunity.narrative_risk_flags)
        plan.comparable_group_id = opportunity.comparable_group_id
        execution_filter_reason_codes = self._execution_filter_reason_codes(
            opportunity,
            reason_codes=list(plan.reason_codes),
            legging_risk_reasons=list(plan.legging_risk_reasons),
            execution_ready=execution_ready,
        )
        plan.execution_filter_reason_codes = list(execution_filter_reason_codes)
        plan.taxonomy = self._assessment_taxonomy(
            opportunity,
            execution_ready=execution_ready,
            reason_codes=list(plan.reason_codes),
            legging_risk_reasons=list(plan.legging_risk_reasons),
        )
        plan.metadata["taxonomy"] = plan.taxonomy.value
        plan.metadata["execution_filter_reason_codes"] = list(plan.execution_filter_reason_codes)
        gross_edge_bps = plan.gross_edge_bps
        estimated_roundtrip_slippage_bps = plan.estimated_roundtrip_slippage_bps
        estimated_fee_bps = plan.estimated_fee_bps

        return ArbitrageAssessment(
            opportunity_id=opportunity.opportunity_id,
            canonical_event_id=opportunity.canonical_event_id,
            verdict=ArbitrageVerdict.executable_candidate if execution_ready else ArbitrageVerdict.signal_only,
            opportunity=opportunity,
            plan=plan,
            execution_ready=execution_ready,
            taxonomy=plan.taxonomy,
            execution_filter_reason_codes=list(execution_filter_reason_codes),
            reason_codes=list(plan.reason_codes),
            comparison_state=opportunity.comparison_state.value,
            narrative_risk_flags=list(opportunity.narrative_risk_flags),
            hedge_completion_ratio=hedge_completion_ratio,
            legging_risk=plan.legging_risk,
            legging_risk_reasons=list(plan.legging_risk_reasons),
            metadata={
                "monitor_class": opportunity.opportunity_class.value,
                "buy_market_id": buy_market_id,
                "sell_market_id": sell_market_id,
                "buy_fill_ratio": buy_report.fill_ratio,
                "sell_fill_ratio": sell_report.fill_ratio,
                "buy_fill_status": buy_report.status.value,
                "sell_fill_status": sell_report.status.value,
                "hedge_completion_ratio": hedge_completion_ratio,
                "hedge_completion_ready": execution_ready,
                "legging_risk_reasons": list(plan.legging_risk_reasons),
                "max_unhedged_leg_ms": self.max_unhedged_leg_ms,
                "taxonomy": plan.taxonomy.value,
                "execution_filter_reason_codes": list(plan.execution_filter_reason_codes),
                "gross_edge_bps": gross_edge_bps,
                "estimated_roundtrip_slippage_bps": estimated_roundtrip_slippage_bps,
                "estimated_fee_bps": estimated_fee_bps,
                "net_edge_bps": net_edge_bps,
                "net_edge_margin_bps": round(net_edge_bps - self.min_net_edge_bps, 6),
            },
        )

    @staticmethod
    def _requires_manual_review(opportunity: SpreadOpportunity) -> bool:
        if opportunity.manual_review_required:
            return True
        if opportunity.comparison_state.value == "manual_review":
            return True
        if ArbitrageLab._execution_like_venue(opportunity.left_venue) or ArbitrageLab._execution_like_venue(opportunity.right_venue):
            return True
        suspicious_flags = {"narrative_only", "weak_question_alignment", "watchlist_only", "no_canonical_event"}
        return any(flag in suspicious_flags for flag in opportunity.narrative_risk_flags)

    @staticmethod
    def _assessment_taxonomy(
        opportunity: SpreadOpportunity,
        *,
        execution_ready: bool,
        reason_codes: list[str],
        legging_risk_reasons: list[str],
    ) -> ArbitrageTaxonomy:
        if opportunity.opportunity_class == SpreadOpportunityClass.comparison_only or opportunity.spread_bps is None:
            return ArbitrageTaxonomy.comparison_only
        if execution_ready:
            return ArbitrageTaxonomy.true_arbitrage
        filter_codes = set(reason_codes) | set(legging_risk_reasons)
        if {"manual_review_required", "execution_like_venue", "narrative_spread_only"} & filter_codes:
            return ArbitrageTaxonomy.cross_venue_signal
        return ArbitrageTaxonomy.relative_value

    @staticmethod
    def _execution_filter_reason_codes(
        opportunity: SpreadOpportunity,
        *,
        reason_codes: list[str],
        legging_risk_reasons: list[str],
        execution_ready: bool,
    ) -> list[str]:
        if execution_ready:
            return []
        filter_codes = list(reason_codes)
        filter_codes.extend(legging_risk_reasons)
        if opportunity.opportunity_class == SpreadOpportunityClass.comparison_only or opportunity.spread_bps is None:
            filter_codes.append("comparison_only")
        if ArbitrageLab._requires_manual_review(opportunity):
            filter_codes.append("manual_review_required")
        return _dedupe(filter_codes)

    @staticmethod
    def _manual_review_reason_code(opportunity: SpreadOpportunity) -> str:
        if ArbitrageLab._execution_like_venue(opportunity.left_venue) or ArbitrageLab._execution_like_venue(opportunity.right_venue):
            return "execution_like_venue"
        suspicious_flags = {"narrative_only", "weak_question_alignment", "watchlist_only", "no_canonical_event"}
        if any(flag in suspicious_flags for flag in opportunity.narrative_risk_flags):
            return "narrative_spread_only"
        if opportunity.manual_review_required:
            return "manual_review_required"
        return "manual_review_required"

    def _legging_risk_reasons(
        self,
        opportunity: SpreadOpportunity,
        *,
        buy_report: SlippageLiquidityReport | None,
        sell_report: SlippageLiquidityReport | None,
        hedge_completion_ratio: float,
    ) -> list[str]:
        reasons: list[str] = []
        if opportunity.manual_review_required:
            reasons.append("manual_review_required")
        if self._execution_like_venue(opportunity.left_venue) or self._execution_like_venue(opportunity.right_venue):
            reasons.append("execution_like_venue")
        if buy_report is None or sell_report is None:
            reasons.append("missing_leg_report")
        else:
            if buy_report.fill_ratio < self.min_fill_ratio or sell_report.fill_ratio < self.min_fill_ratio:
                reasons.append("hedge_completion_below_threshold")
            fill_gap = abs(buy_report.fill_ratio - sell_report.fill_ratio)
            if fill_gap > 0.05:
                reasons.append("hedge_completion_imbalance")
            if buy_report.status == SlippageLiquidityStatus.partial or sell_report.status == SlippageLiquidityStatus.partial:
                reasons.append("partial_fill")
            if buy_report.status == SlippageLiquidityStatus.rejected or sell_report.status == SlippageLiquidityStatus.rejected:
                reasons.append("rejected_leg")
        if hedge_completion_ratio < self.min_fill_ratio:
            reasons.append("hedge_completion_incomplete")
        if self.max_unhedged_leg_ms > 0:
            reasons.append(f"unhedged_leg_window:{self.max_unhedged_leg_ms}")
        return _dedupe(reasons)

    @staticmethod
    def _execution_like_venue(venue: VenueName) -> bool:
        surface = DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(venue)
        return bool(surface.execution_role in {"execution_like", "execution_bindable"} and not surface.execution_equivalent)

    def _plan_from_opportunity(
        self,
        opportunity: SpreadOpportunity,
        *,
        buy_report: SlippageLiquidityReport | None,
        sell_report: SlippageLiquidityReport | None,
        executable: bool,
        reason_codes: list[str] | None = None,
    ) -> ArbitragePlan:
        reason_codes = list(reason_codes or [])
        buy_leg = self._leg_plan("buy", opportunity, buy_report) if buy_report is not None else None
        sell_leg = self._leg_plan("sell", opportunity, sell_report) if sell_report is not None else None
        gross_edge_bps = opportunity.spread_bps or 0.0
        estimated_roundtrip_slippage_bps = 0.0
        estimated_fee_bps = 2.0 * self.fee_bps
        if buy_report is not None and sell_report is not None:
            estimated_roundtrip_slippage_bps = abs(buy_report.slippage_bps) + abs(sell_report.slippage_bps)
        net_edge_bps = max(0.0, gross_edge_bps - estimated_roundtrip_slippage_bps - estimated_fee_bps)
        if not buy_report or not sell_report:
            reason_codes.append("missing_leg_report")
        if net_edge_bps < self.min_net_edge_bps:
            reason_codes.append("net_edge_below_threshold")
        return ArbitragePlan(
            opportunity_id=opportunity.opportunity_id,
            canonical_event_id=opportunity.canonical_event_id,
            verdict=ArbitrageVerdict.executable_candidate if executable else ArbitrageVerdict.signal_only,
            direction=opportunity.direction,
            spread_bps=opportunity.spread_bps or 0.0,
            gross_edge_bps=gross_edge_bps,
            estimated_roundtrip_slippage_bps=estimated_roundtrip_slippage_bps,
            estimated_fee_bps=estimated_fee_bps,
            net_edge_bps=net_edge_bps,
            executable=executable,
            buy_leg=buy_leg,
            sell_leg=sell_leg,
            reason_codes=_dedupe(reason_codes),
            metadata={
                "opportunity_class": opportunity.opportunity_class.value,
                "probe_quantity": self.probe_quantity,
                "buy_snapshot_id": opportunity.buy_snapshot_id,
                "sell_snapshot_id": opportunity.sell_snapshot_id,
                "max_unhedged_leg_ms": self.max_unhedged_leg_ms,
            },
        )

    def _leg_plan(self, kind: str, opportunity: SpreadOpportunity, report: SlippageLiquidityReport) -> ArbitrageLegPlan:
        market_id = opportunity.preferred_buy_market_id if kind == "buy" else opportunity.preferred_sell_market_id
        venue = report.venue
        if market_id is None:
            market_id = opportunity.left_market_id if kind == "buy" else opportunity.right_market_id
        return ArbitrageLegPlan(
            opportunity_id=opportunity.opportunity_id,
            market_id=market_id,
            venue=venue,
            position_side=report.position_side,
            execution_side=report.execution_side,
            requested_quantity=report.requested_quantity,
            requested_notional=report.requested_notional,
            filled_quantity=report.filled_quantity,
            filled_notional=report.filled_notional,
            average_fill_price=report.average_fill_price,
            slippage_bps=report.slippage_bps,
            fee_paid=report.fee_paid,
            fill_ratio=report.fill_ratio,
            status=report.status,
            snapshot_id=report.snapshot_id,
            source="orderbook" if not report.synthetic_reference else "synthetic_reference",
            metadata=report.to_execution_metadata(),
        )


def assess_arbitrage(
    markets: list[MarketDescriptor],
    *,
    snapshots: dict[str, MarketSnapshot] | None = None,
    matches: list[CrossVenueMatch] | None = None,
    lab: ArbitrageLab | None = None,
) -> ArbitrageLabReport:
    return (lab or ArbitrageLab()).assess(markets, snapshots=snapshots, matches=matches)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
