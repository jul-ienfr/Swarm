from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from .cross_venue import CrossVenueIntelligence, CrossVenueMatch, CrossVenueOpsState, SpreadSeverity
from .market_graph import ComparableMarketGroup
from .models import MarketDescriptor, MarketSnapshot, TradeSide, VenueName, VenueType
from .slippage_liquidity import SlippageLiquidityReport, SlippageLiquiditySimulator, SlippageLiquidityStatus


class SpreadOpportunityClass(str, Enum):
    comparison_only = "comparison_only"
    signal_only = "signal_only"
    executable_candidate = "executable_candidate"


class SpreadOpportunityDirection(str, Enum):
    buy_left_sell_right = "buy_left_sell_right"
    buy_right_sell_left = "buy_right_sell_left"
    unknown = "unknown"


class SpreadMonitorAlert(BaseModel):
    schema_version: str = "v1"
    alert_id: str = Field(default_factory=lambda: f"spalert_{uuid4().hex[:12]}")
    opportunity_id: str
    severity: SpreadSeverity = SpreadSeverity.low
    spread_bps: float
    threshold_bps: float
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpreadOpportunity(BaseModel):
    schema_version: str = "v1"
    opportunity_id: str = Field(default_factory=lambda: f"spop_{uuid4().hex[:12]}")
    comparison_id: str | None = None
    match_id: str | None = None
    canonical_event_id: str
    left_market_id: str
    right_market_id: str
    left_venue: VenueName
    right_venue: VenueName
    left_probability: float | None = None
    right_probability: float | None = None
    probability_delta: float | None = None
    spread_bps: float | None = None
    direction: SpreadOpportunityDirection = SpreadOpportunityDirection.unknown
    opportunity_class: SpreadOpportunityClass = SpreadOpportunityClass.comparison_only
    reference_market_id: str | None = None
    comparison_market_id: str | None = None
    comparable_group_id: str | None = None
    preferred_buy_market_id: str | None = None
    preferred_sell_market_id: str | None = None
    compatible_resolution: bool = False
    manual_review_required: bool = True
    match_similarity: float | None = None
    reason_codes: list[str] = Field(default_factory=list)
    narrative_risk_flags: list[str] = Field(default_factory=list)
    comparison_state: CrossVenueOpsState = CrossVenueOpsState.comparison_only
    comparison_summary: str = ""
    spread_severity: SpreadSeverity = SpreadSeverity.low
    buy_snapshot_id: str | None = None
    sell_snapshot_id: str | None = None
    buy_fill_report: SlippageLiquidityReport | None = None
    sell_fill_report: SlippageLiquidityReport | None = None
    estimated_roundtrip_slippage_bps: float | None = None
    estimated_net_edge_bps: float | None = None
    liquidity_supported: bool = False
    probe_quantity: float = 0.0
    probe_fee_bps: float = 0.0
    alert_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def executable(self) -> bool:
        return self.opportunity_class == SpreadOpportunityClass.executable_candidate


class SpreadMonitorReport(BaseModel):
    schema_version: str = "v1"
    report_id: str = Field(default_factory=lambda: f"spmon_{uuid4().hex[:12]}")
    opportunities: list[SpreadOpportunity] = Field(default_factory=list)
    alerts: list[SpreadMonitorAlert] = Field(default_factory=list)
    comparison_count: int = 0
    signal_count: int = 0
    executable_count: int = 0
    manual_review_count: int = 0
    narrative_risk_count: int = 0
    comparison_state_counts: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class SpreadMonitor:
    match_threshold: float = 0.6
    signal_threshold_bps: float = 50.0
    executable_threshold_bps: float = 100.0
    max_staleness_ms: int = 120_000
    max_slippage_bps: float = 120.0
    min_liquidity: float = 0.0
    probe_quantity: float = 10.0
    probe_fee_bps: float = 0.0
    execution_fill_ratio_floor: float = 0.95
    alert_threshold_bps: float = 120.0
    cross_venue: CrossVenueIntelligence = field(default_factory=CrossVenueIntelligence)
    slippage_simulator: SlippageLiquiditySimulator = field(default_factory=SlippageLiquiditySimulator)

    def scan(
        self,
        markets: list[MarketDescriptor],
        *,
        snapshots: dict[str, MarketSnapshot] | None = None,
        matches: list[CrossVenueMatch] | None = None,
    ) -> SpreadMonitorReport:
        snapshots = snapshots or {}
        graph = self.cross_venue.graph_builder.build(markets, snapshots=snapshots)
        group_by_market_id = graph.comparable_group_index()
        if matches is None:
            matches = list(graph.matches)
        opportunities: list[SpreadOpportunity] = []
        alerts: list[SpreadMonitorAlert] = []

        for match in matches:
            opportunity = self._classify_match(match, markets, snapshots, group_by_market_id=group_by_market_id)
            opportunities.append(opportunity)
            if opportunity.spread_bps is not None and opportunity.spread_bps >= self.alert_threshold_bps:
                alerts.append(
                    SpreadMonitorAlert(
                        opportunity_id=opportunity.opportunity_id,
                        severity=opportunity.spread_severity,
                        spread_bps=opportunity.spread_bps,
                        threshold_bps=self.alert_threshold_bps,
                        message=(
                            f"Cross-venue spread {opportunity.spread_bps:.2f} bps "
                            f"exceeds alert threshold {self.alert_threshold_bps:.2f} bps."
                        ),
                        metadata={
                            "canonical_event_id": opportunity.canonical_event_id,
                            "left_market_id": opportunity.left_market_id,
                            "right_market_id": opportunity.right_market_id,
                        },
                    )
                )

        comparison_count = sum(1 for opportunity in opportunities if opportunity.opportunity_class == SpreadOpportunityClass.comparison_only)
        signal_count = sum(1 for opportunity in opportunities if opportunity.opportunity_class == SpreadOpportunityClass.signal_only)
        executable_count = sum(1 for opportunity in opportunities if opportunity.opportunity_class == SpreadOpportunityClass.executable_candidate)
        manual_review_count = sum(1 for opportunity in opportunities if opportunity.manual_review_required)
        narrative_risk_count = sum(len(opportunity.narrative_risk_flags) for opportunity in opportunities)
        comparison_state_counts: dict[str, int] = {}
        for opportunity in opportunities:
            comparison_state_counts[opportunity.comparison_state.value] = comparison_state_counts.get(opportunity.comparison_state.value, 0) + 1
        return SpreadMonitorReport(
            opportunities=opportunities,
            alerts=alerts,
            comparison_count=comparison_count,
            signal_count=signal_count,
            executable_count=executable_count,
            manual_review_count=manual_review_count,
            narrative_risk_count=narrative_risk_count,
            comparison_state_counts=comparison_state_counts,
            metadata={
                "market_count": len(markets),
                "match_count": len(matches),
                "signal_threshold_bps": self.signal_threshold_bps,
                "executable_threshold_bps": self.executable_threshold_bps,
                "probe_quantity": self.probe_quantity,
                "max_slippage_bps": self.max_slippage_bps,
            },
        )

    def _classify_match(
        self,
        match: CrossVenueMatch,
        markets: list[MarketDescriptor],
        snapshots: dict[str, MarketSnapshot],
        *,
        group_by_market_id: dict[str, ComparableMarketGroup] | None = None,
    ) -> SpreadOpportunity:
        left = self._get_market(markets, match.left_market_id)
        right = self._get_market(markets, match.right_market_id)
        left_snapshot = snapshots.get(left.market_id)
        right_snapshot = snapshots.get(right.market_id)
        left_probability = self._probability(left_snapshot)
        right_probability = self._probability(right_snapshot)
        probability_delta = None
        spread_bps = None
        if left_probability is not None and right_probability is not None:
            probability_delta = round(left_probability - right_probability, 6)
            spread_bps = round(abs(probability_delta) * 10000.0, 2)

        direction, buy_market_id, sell_market_id = self._direction(left.market_id, right.market_id, probability_delta)
        reference_market_id, comparison_market_id = self._reference_pair(left, right)
        comparison_id = f"spcmp_{match.match_id}"
        reason_codes: list[str] = []
        opportunity_class = SpreadOpportunityClass.comparison_only
        spread_severity = self._severity_for_spread(spread_bps or 0.0)
        narrative_risk_flags = self._narrative_risk_flags(match, left, right, spread_bps)
        comparable_group_id = None
        group = None
        if group_by_market_id is not None:
            group = group_by_market_id.get(left.market_id) or group_by_market_id.get(right.market_id)
        if group is not None:
            comparable_group_id = group.group_id
            if group.narrative_risk_flags:
                narrative_risk_flags = list(dict.fromkeys(narrative_risk_flags + group.narrative_risk_flags))
        review_reason_codes = self._review_reason_codes(match, narrative_risk_flags, spread_bps)
        manual_review_required = bool(review_reason_codes)

        signal_snapshot_buy: MarketSnapshot | None = None
        signal_snapshot_sell: MarketSnapshot | None = None
        feasibility: dict[str, Any] = {
            "executable": False,
            "reason_codes": [],
            "buy_report": None,
            "sell_report": None,
            "roundtrip_slippage_bps": None,
            "net_edge_bps": None,
            "liquidity_supported": False,
        }

        if spread_bps is None:
            reason_codes.append("missing_probability")
        elif review_reason_codes:
            reason_codes.extend(review_reason_codes)
            opportunity_class = SpreadOpportunityClass.signal_only
        elif spread_bps < self.signal_threshold_bps:
            reason_codes.append("spread_below_signal_threshold")
        else:
            signal_snapshot_buy = snapshots.get(buy_market_id or "")
            signal_snapshot_sell = snapshots.get(sell_market_id or "")
            feasibility = self._execution_feasibility(
                buy_snapshot=signal_snapshot_buy,
                sell_snapshot=signal_snapshot_sell,
                buy_market_id=buy_market_id,
                sell_market_id=sell_market_id,
                position_side=TradeSide.yes,
                spread_bps=spread_bps,
            )
            reason_codes.extend(feasibility["reason_codes"])
            narrative_risk_flags = list(
                dict.fromkeys(narrative_risk_flags + self._risk_flags_from_reason_codes(reason_codes))
            )
            if feasibility["executable"] and not self._requires_manual_review(match, narrative_risk_flags, spread_bps):
                opportunity_class = SpreadOpportunityClass.executable_candidate
            else:
                opportunity_class = SpreadOpportunityClass.signal_only
                if feasibility["executable"] and "narrative_spread_only" not in reason_codes:
                    reason_codes.append("narrative_spread_only")

            comparison_state = self._comparison_state(opportunity_class, match, spread_bps, reason_codes)
            comparison_summary = self._comparison_summary(
                opportunity_class=opportunity_class,
                comparison_state=comparison_state,
                spread_bps=spread_bps,
                reason_codes=reason_codes,
                narrative_risk_flags=narrative_risk_flags,
            )
            return SpreadOpportunity(
                comparison_id=comparison_id,
                match_id=match.match_id,
                canonical_event_id=match.canonical_event_id,
                left_market_id=left.market_id,
                right_market_id=right.market_id,
                left_venue=left.venue,
                right_venue=right.venue,
                left_probability=left_probability,
                right_probability=right_probability,
                probability_delta=probability_delta,
                spread_bps=spread_bps,
                direction=direction,
                opportunity_class=opportunity_class,
                reference_market_id=reference_market_id,
                comparison_market_id=comparison_market_id,
                comparable_group_id=comparable_group_id,
                preferred_buy_market_id=buy_market_id,
                preferred_sell_market_id=sell_market_id,
                compatible_resolution=match.compatible_resolution,
                manual_review_required=manual_review_required,
                match_similarity=match.similarity,
                reason_codes=reason_codes,
                narrative_risk_flags=narrative_risk_flags,
                comparison_state=comparison_state,
                comparison_summary=comparison_summary,
                spread_severity=spread_severity,
                buy_snapshot_id=None if signal_snapshot_buy is None else signal_snapshot_buy.snapshot_id,
                sell_snapshot_id=None if signal_snapshot_sell is None else signal_snapshot_sell.snapshot_id,
                buy_fill_report=feasibility["buy_report"],
                sell_fill_report=feasibility["sell_report"],
                estimated_roundtrip_slippage_bps=feasibility["roundtrip_slippage_bps"],
                estimated_net_edge_bps=feasibility["net_edge_bps"],
                liquidity_supported=feasibility["liquidity_supported"],
                probe_quantity=self.probe_quantity,
                probe_fee_bps=self.probe_fee_bps,
                metadata={
                    "match_id": match.match_id,
                    "match_similarity": match.similarity,
                    "manual_review_required": manual_review_required,
                    "reference_market_id": reference_market_id,
                    "comparison_market_id": comparison_market_id,
                    "comparable_group_id": comparable_group_id,
                    "narrative_risk_flags": narrative_risk_flags,
                    "comparison_state": comparison_state.value,
                    "spread_threshold_bps": self.signal_threshold_bps,
                },
            )

        augmented_narrative_risk_flags = list(dict.fromkeys(narrative_risk_flags + self._risk_flags_from_reason_codes(reason_codes)))
        comparison_state = self._comparison_state(opportunity_class, match, spread_bps, reason_codes)
        comparison_summary = self._comparison_summary(
            opportunity_class=opportunity_class,
            comparison_state=comparison_state,
            spread_bps=spread_bps,
            reason_codes=reason_codes,
            narrative_risk_flags=augmented_narrative_risk_flags,
        )
        return SpreadOpportunity(
            comparison_id=comparison_id,
            match_id=match.match_id,
            canonical_event_id=match.canonical_event_id,
            left_market_id=left.market_id,
            right_market_id=right.market_id,
            left_venue=left.venue,
            right_venue=right.venue,
            left_probability=left_probability,
            right_probability=right_probability,
            probability_delta=probability_delta,
            spread_bps=spread_bps,
            direction=direction,
            opportunity_class=opportunity_class,
            reference_market_id=reference_market_id,
            comparison_market_id=comparison_market_id,
            comparable_group_id=comparable_group_id,
            preferred_buy_market_id=buy_market_id,
            preferred_sell_market_id=sell_market_id,
            compatible_resolution=match.compatible_resolution,
            manual_review_required=manual_review_required,
            match_similarity=match.similarity,
            reason_codes=reason_codes,
            narrative_risk_flags=augmented_narrative_risk_flags,
            comparison_state=comparison_state,
            comparison_summary=comparison_summary,
            spread_severity=spread_severity,
            buy_snapshot_id=None if left_snapshot is None else left_snapshot.snapshot_id,
            sell_snapshot_id=None if right_snapshot is None else right_snapshot.snapshot_id,
            probe_quantity=self.probe_quantity,
            probe_fee_bps=self.probe_fee_bps,
            metadata={
                "match_id": match.match_id,
                "match_similarity": match.similarity,
                "manual_review_required": manual_review_required,
                "reference_market_id": reference_market_id,
                "comparison_market_id": comparison_market_id,
                "comparable_group_id": comparable_group_id,
                "narrative_risk_flags": augmented_narrative_risk_flags,
                "comparison_state": comparison_state.value,
                "comparison_summary": comparison_summary,
                "spread_threshold_bps": self.signal_threshold_bps,
            },
        )

    @staticmethod
    def _risk_flags_from_reason_codes(reason_codes: list[str]) -> list[str]:
        flags: list[str] = []
        mapping = {
            "missing_probability": "missing_probability",
            "incompatible_resolution": "resolution_mismatch",
            "manual_review_required": "manual_review_required",
            "narrative_spread_only": "narrative_only",
            "narrative_only": "narrative_only",
            "spread_below_signal_threshold": "comparison_only",
            "missing_snapshot": "missing_snapshot",
            "missing_orderbook": "missing_orderbook",
            "buy_snapshot_stale": "stale_snapshot",
            "sell_snapshot_stale": "stale_snapshot",
            "buy_liquidity_below_minimum": "insufficient_liquidity",
            "sell_liquidity_below_minimum": "insufficient_liquidity",
            "insufficient_liquidity": "insufficient_liquidity",
        }
        for code in reason_codes:
            flag = mapping.get(code)
            if flag is not None and flag not in flags:
                flags.append(flag)
        return flags

    def _comparison_state(
        self,
        opportunity_class: SpreadOpportunityClass,
        match: CrossVenueMatch,
        spread_bps: float | None,
        reason_codes: list[str],
    ) -> CrossVenueOpsState:
        if (
            match.manual_review_required
            or not match.compatible_resolution
            or "manual_review_required" in reason_codes
            or "incompatible_resolution" in reason_codes
            or "narrative_spread_only" in reason_codes
            or "narrative_only" in reason_codes
        ):
            return CrossVenueOpsState.manual_review
        if spread_bps is None or "missing_probability" in reason_codes or "spread_below_signal_threshold" in reason_codes:
            return CrossVenueOpsState.comparison_only
        if spread_bps >= self.alert_threshold_bps:
            return CrossVenueOpsState.spread_alert
        if opportunity_class == SpreadOpportunityClass.executable_candidate:
            return CrossVenueOpsState.executable_candidate
        if opportunity_class == SpreadOpportunityClass.signal_only:
            return CrossVenueOpsState.signal_only
        return CrossVenueOpsState.comparison_only

    @staticmethod
    def _comparison_summary(
        *,
        opportunity_class: SpreadOpportunityClass,
        comparison_state: CrossVenueOpsState,
        spread_bps: float | None,
        reason_codes: list[str],
        narrative_risk_flags: list[str],
    ) -> str:
        spread_text = "spread=unknown" if spread_bps is None else f"spread={spread_bps:.2f}bps"
        reasons = ", ".join(reason_codes[:3]) if reason_codes else "no_reason_codes"
        risks = ", ".join(narrative_risk_flags[:3]) if narrative_risk_flags else "no_narrative_risks"
        return (
            f"class={opportunity_class.value}; state={comparison_state.value}; {spread_text}; "
            f"reasons={reasons}; risks={risks}"
        )

    @staticmethod
    def _narrative_risk_flags(
        match: CrossVenueMatch,
        left: MarketDescriptor,
        right: MarketDescriptor,
        spread_bps: float | None,
    ) -> list[str]:
        flags: list[str] = []
        if match.manual_review_required:
            flags.append("manual_review_required")
        if not match.compatible_resolution:
            flags.append("resolution_mismatch")
        if spread_bps is None:
            flags.append("missing_probability")
        elif spread_bps >= 50.0 and match.similarity < 0.8:
            flags.append("narrative_only")
        elif spread_bps < 20.0 and match.similarity < 0.7:
            flags.append("weak_question_alignment")
        if left.canonical_event_id is None and right.canonical_event_id is None:
            flags.append("no_canonical_event")
        if left.venue_type == VenueType.watchlist and right.venue_type == VenueType.watchlist:
            flags.append("watchlist_only")
        return list(dict.fromkeys(flags))

    @staticmethod
    def _review_reason_codes(
        match: CrossVenueMatch,
        narrative_risk_flags: list[str],
        spread_bps: float | None,
    ) -> list[str]:
        reasons: list[str] = []
        if not match.compatible_resolution:
            reasons.append("incompatible_resolution")
        if match.manual_review_required:
            reasons.append("manual_review_required")
        if spread_bps is not None and spread_bps >= 50.0:
            severe_flags = {"narrative_only", "weak_question_alignment", "watchlist_only", "no_canonical_event"}
            if any(flag in severe_flags for flag in narrative_risk_flags):
                reasons.append("narrative_spread_only")
        return list(dict.fromkeys(reasons))

    @staticmethod
    def _requires_manual_review(
        match: CrossVenueMatch,
        narrative_risk_flags: list[str],
        spread_bps: float | None,
    ) -> bool:
        if match.manual_review_required or not match.compatible_resolution:
            return True
        if spread_bps is None:
            return False
        severe_flags = {"narrative_only", "weak_question_alignment", "watchlist_only", "no_canonical_event"}
        return any(flag in severe_flags for flag in narrative_risk_flags)

    def _execution_feasibility(
        self,
        *,
        buy_snapshot: MarketSnapshot | None,
        sell_snapshot: MarketSnapshot | None,
        buy_market_id: str | None,
        sell_market_id: str | None,
        position_side: TradeSide,
        spread_bps: float,
    ) -> dict[str, Any]:
        reason_codes: list[str] = []
        if buy_snapshot is None or sell_snapshot is None:
            return {
                "executable": False,
                "reason_codes": ["missing_snapshot"],
                "buy_report": None,
                "sell_report": None,
                "roundtrip_slippage_bps": None,
                "net_edge_bps": None,
                "liquidity_supported": False,
            }
        if buy_snapshot.orderbook is None or sell_snapshot.orderbook is None:
            return {
                "executable": False,
                "reason_codes": ["missing_orderbook"],
                "buy_report": None,
                "sell_report": None,
                "roundtrip_slippage_bps": None,
                "net_edge_bps": None,
                "liquidity_supported": False,
            }
        if buy_snapshot.staleness_ms is not None and buy_snapshot.staleness_ms > self.max_staleness_ms:
            reason_codes.append("buy_snapshot_stale")
        if sell_snapshot.staleness_ms is not None and sell_snapshot.staleness_ms > self.max_staleness_ms:
            reason_codes.append("sell_snapshot_stale")
        if buy_snapshot.liquidity is not None and buy_snapshot.liquidity < self.min_liquidity:
            reason_codes.append("buy_liquidity_below_minimum")
        if sell_snapshot.liquidity is not None and sell_snapshot.liquidity < self.min_liquidity:
            reason_codes.append("sell_liquidity_below_minimum")
        if reason_codes:
            return {
                "executable": False,
                "reason_codes": reason_codes,
                "buy_report": None,
                "sell_report": None,
                "roundtrip_slippage_bps": None,
                "net_edge_bps": None,
                "liquidity_supported": False,
            }

        simulator = SlippageLiquiditySimulator(fee_bps=self.probe_fee_bps, max_slippage_bps=self.max_slippage_bps)
        buy_report = simulator.simulate(
            buy_snapshot,
            position_side=position_side,
            execution_side=TradeSide.buy,
            requested_quantity=self.probe_quantity,
            run_id=f"slip_{uuid4().hex[:12]}",
            market_id=buy_market_id,
        )
        sell_report = simulator.simulate(
            sell_snapshot,
            position_side=position_side,
            execution_side=TradeSide.sell,
            requested_quantity=self.probe_quantity,
            run_id=f"slip_{uuid4().hex[:12]}",
            market_id=sell_market_id,
        )
        roundtrip_slippage_bps = abs(buy_report.slippage_bps) + abs(sell_report.slippage_bps)
        net_edge_bps = max(0.0, spread_bps - roundtrip_slippage_bps - (2.0 * self.probe_fee_bps))
        liquidity_supported = (
            buy_report.status in {SlippageLiquidityStatus.filled, SlippageLiquidityStatus.partial}
            and sell_report.status in {SlippageLiquidityStatus.filled, SlippageLiquidityStatus.partial}
            and buy_report.fill_ratio >= self.execution_fill_ratio_floor
            and sell_report.fill_ratio >= self.execution_fill_ratio_floor
            and buy_report.synthetic_reference is False
            and sell_report.synthetic_reference is False
        )
        executable = liquidity_supported and net_edge_bps >= self.executable_threshold_bps
        if not liquidity_supported:
            reason_codes.append("insufficient_liquidity")
        if net_edge_bps < self.executable_threshold_bps:
            reason_codes.append("net_edge_below_threshold")
        return {
            "executable": executable,
            "reason_codes": reason_codes,
            "buy_report": buy_report,
            "sell_report": sell_report,
            "roundtrip_slippage_bps": roundtrip_slippage_bps,
            "net_edge_bps": net_edge_bps,
            "liquidity_supported": liquidity_supported,
        }

    @staticmethod
    def _get_market(markets: list[MarketDescriptor], market_id: str) -> MarketDescriptor:
        for market in markets:
            if market.market_id == market_id:
                return market
        raise KeyError(market_id)

    @staticmethod
    def _probability(snapshot: MarketSnapshot | None) -> float | None:
        if snapshot is None:
            return None
        for candidate in (
            snapshot.market_implied_probability,
            snapshot.fair_probability_hint,
            snapshot.midpoint_yes,
            snapshot.price_yes,
        ):
            if candidate is not None:
                return max(0.0, min(1.0, float(candidate)))
        return None

    @staticmethod
    def _direction(left_market_id: str, right_market_id: str, probability_delta: float | None) -> tuple[SpreadOpportunityDirection, str | None, str | None]:
        if probability_delta is None:
            return SpreadOpportunityDirection.unknown, None, None
        if probability_delta > 0:
            return SpreadOpportunityDirection.buy_right_sell_left, right_market_id, left_market_id
        if probability_delta < 0:
            return SpreadOpportunityDirection.buy_left_sell_right, left_market_id, right_market_id
        return SpreadOpportunityDirection.unknown, None, None

    @staticmethod
    def _reference_pair(left: MarketDescriptor, right: MarketDescriptor) -> tuple[str | None, str | None]:
        if left.venue_type == VenueType.reference and right.venue_type != VenueType.reference:
            return left.market_id, right.market_id
        if right.venue_type == VenueType.reference and left.venue_type != VenueType.reference:
            return right.market_id, left.market_id
        if left.clarity_score >= right.clarity_score:
            return left.market_id, right.market_id
        return right.market_id, left.market_id

    @staticmethod
    def _severity_for_spread(spread_bps: float) -> SpreadSeverity:
        if spread_bps >= 200:
            return SpreadSeverity.high
        if spread_bps >= 120:
            return SpreadSeverity.medium
        return SpreadSeverity.low


def monitor_spreads(
    markets: list[MarketDescriptor],
    *,
    snapshots: dict[str, MarketSnapshot] | None = None,
    matches: list[CrossVenueMatch] | None = None,
    monitor: SpreadMonitor | None = None,
) -> SpreadMonitorReport:
    return (monitor or SpreadMonitor()).scan(markets, snapshots=snapshots, matches=matches)
