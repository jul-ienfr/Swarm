from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from .models import MarketOrderBook, MarketSnapshot, TradeSide, VenueName


class SlippageLiquidityStatus(str, Enum):
    filled = "filled"
    partial = "partial"
    no_liquidity = "no_liquidity"
    synthetic = "synthetic"
    rejected = "rejected"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SlippageLiquidityFill(BaseModel):
    schema_version: str = "v1"
    fill_id: str = Field(default_factory=lambda: f"slipfill_{uuid4().hex[:12]}")
    market_id: str
    venue: VenueName
    position_side: TradeSide
    execution_side: TradeSide
    level_index: int | None = None
    source: str = "orderbook"
    requested_quantity: float = 0.0
    filled_quantity: float = 0.0
    fill_price: float = 0.0
    gross_notional: float = 0.0
    cumulative_quantity: float = 0.0
    cumulative_notional: float = 0.0
    marginal_slippage_bps: float = 0.0
    signed_slippage_bps: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "requested_quantity",
        "filled_quantity",
        "fill_price",
        "gross_notional",
        "cumulative_quantity",
        "cumulative_notional",
    )
    @classmethod
    def _non_negative(cls, value: float) -> float:
        return max(0.0, float(value))


class SlippageLiquidityCurvePoint(BaseModel):
    schema_version: str = "v1"
    point_id: str = Field(default_factory=lambda: f"slipcurve_{uuid4().hex[:12]}")
    market_id: str
    venue: VenueName
    position_side: TradeSide
    execution_side: TradeSide
    level_index: int
    level_price: float
    level_quantity: float
    cumulative_quantity: float
    cumulative_notional: float
    average_fill_price: float
    marginal_slippage_bps: float
    remaining_quantity: float
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "level_price",
        "level_quantity",
        "cumulative_quantity",
        "cumulative_notional",
        "average_fill_price",
        "remaining_quantity",
    )
    @classmethod
    def _non_negative(cls, value: float) -> float:
        return max(0.0, float(value))


class SlippageLiquidityRequest(BaseModel):
    schema_version: str = "v1"
    request_id: str = Field(default_factory=lambda: f"slipreq_{uuid4().hex[:12]}")
    run_id: str | None = None
    market_id: str
    venue: VenueName = VenueName.polymarket
    snapshot_id: str | None = None
    position_side: TradeSide = TradeSide.yes
    execution_side: TradeSide = TradeSide.buy
    requested_quantity: float | None = None
    requested_notional: float | None = None
    limit_price: float | None = None
    fee_bps: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("requested_quantity", "requested_notional", "limit_price", "fee_bps")
    @classmethod
    def _normalize_numeric(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return float(value)

    @model_validator(mode="after")
    def _normalize(self) -> "SlippageLiquidityRequest":
        if self.position_side not in {TradeSide.yes, TradeSide.no}:
            raise ValueError("position_side must be yes or no.")
        if self.execution_side not in {TradeSide.buy, TradeSide.sell}:
            raise ValueError("execution_side must be buy or sell.")
        if self.requested_quantity is not None and self.requested_quantity < 0:
            self.requested_quantity = 0.0
        if self.requested_notional is not None and self.requested_notional < 0:
            self.requested_notional = 0.0
        if self.limit_price is not None:
            self.limit_price = max(0.0, min(1.0, float(self.limit_price)))
        self.fee_bps = max(0.0, float(self.fee_bps))
        return self


class SlippageLiquidityReport(BaseModel):
    schema_version: str = "v1"
    report_id: str = Field(default_factory=lambda: f"sliprpt_{uuid4().hex[:12]}")
    request_id: str
    run_id: str
    market_id: str
    venue: VenueName
    snapshot_id: str | None = None
    position_side: TradeSide
    execution_side: TradeSide
    status: SlippageLiquidityStatus = SlippageLiquidityStatus.no_liquidity
    requested_quantity: float = 0.0
    requested_notional: float = 0.0
    filled_quantity: float = 0.0
    filled_notional: float = 0.0
    remaining_quantity: float = 0.0
    fill_ratio: float = 0.0
    reference_price: float = 0.0
    top_of_book_price: float | None = None
    spread_mean_bps: float | None = None
    average_fill_price: float | None = None
    best_fill_price: float | None = None
    worst_fill_price: float | None = None
    spread_bps: float | None = None
    slippage_bps: float = 0.0
    closing_line_drift_bps: float = 0.0
    fee_paid: float = 0.0
    liquidity_available_quantity: float = 0.0
    liquidity_available_notional: float = 0.0
    liquidity_consumed_fraction: float = 0.0
    fill_count: int = 0
    average_fill_quantity: float = 0.0
    fragmented: bool = False
    fragmentation_score: float = 0.0
    market_fit_status: str = "unknown"
    market_fit_score: float = 0.0
    shadow_eligible: bool = False
    market_fit_reasons: list[str] = Field(default_factory=list)
    gross_cash_flow: float = 0.0
    net_cash_flow: float = 0.0
    effective_price_after_fees: float | None = None
    synthetic_reference: bool = False
    partial_fill: bool = False
    limit_price: float | None = None
    no_trade_reasons: list[str] = Field(default_factory=list)
    fills: list[SlippageLiquidityFill] = Field(default_factory=list)
    curve: list[SlippageLiquidityCurvePoint] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "requested_quantity",
        "requested_notional",
        "filled_quantity",
        "filled_notional",
        "remaining_quantity",
        "fill_ratio",
        "reference_price",
        "slippage_bps",
        "closing_line_drift_bps",
        "fee_paid",
        "liquidity_available_quantity",
        "liquidity_available_notional",
        "liquidity_consumed_fraction",
    )
    @classmethod
    def _non_negative(cls, value: float) -> float:
        return max(0.0, float(value))

    @model_validator(mode="after")
    def _derive(self) -> "SlippageLiquidityReport":
        self.fill_count = len(self.fills)
        if self.filled_quantity > 0 and self.average_fill_price is None:
            self.average_fill_price = round(self.filled_notional / self.filled_quantity, 6)
        if self.best_fill_price is None and self.fills:
            self.best_fill_price = min(fill.fill_price for fill in self.fills)
        if self.worst_fill_price is None and self.fills:
            self.worst_fill_price = max(fill.fill_price for fill in self.fills)
        if self.requested_quantity > 0 and self.fill_ratio == 0.0:
            self.fill_ratio = round(min(1.0, self.filled_quantity / self.requested_quantity), 6)
        self.partial_fill = self.status == SlippageLiquidityStatus.partial or (
            self.requested_quantity > 0 and self.filled_quantity + 1e-12 < self.requested_quantity and self.filled_quantity > 0
        )
        self.remaining_quantity = max(0.0, float(self.requested_quantity - self.filled_quantity))
        self.average_fill_quantity = 0.0 if self.fill_count <= 0 else round(self.filled_quantity / self.fill_count, 6)
        self.fragmented = self.fill_count > 1
        self.fragmentation_score = 0.0
        if self.fragmented and self.filled_quantity > 0:
            largest_fill = max(fill.filled_quantity for fill in self.fills)
            self.fragmentation_score = round(1.0 - min(1.0, largest_fill / self.filled_quantity), 6)
        self.gross_cash_flow = self.filled_notional if self.execution_side == TradeSide.sell else -self.filled_notional
        self.net_cash_flow = self.gross_cash_flow - self.fee_paid
        if self.filled_quantity > 0:
            self.effective_price_after_fees = round(abs(self.net_cash_flow) / self.filled_quantity, 6)
        market_fit_reasons: list[str] = []
        if self.status == SlippageLiquidityStatus.filled:
            market_fit_status = "fit"
            market_fit_score = 1.0
        elif self.status == SlippageLiquidityStatus.partial:
            market_fit_status = "partial_fit"
            market_fit_score = round(min(1.0, max(0.0, self.fill_ratio)), 6)
            market_fit_reasons.append("partial_fill")
        elif self.status == SlippageLiquidityStatus.synthetic:
            market_fit_status = "synthetic_reference"
            market_fit_score = 0.75
            market_fit_reasons.append("synthetic_reference")
        elif self.status == SlippageLiquidityStatus.no_liquidity:
            market_fit_status = "no_liquidity"
            market_fit_score = 0.0
            market_fit_reasons.append("no_liquidity")
        else:
            market_fit_status = "rejected"
            market_fit_score = 0.0
            market_fit_reasons.append("rejected")
        if self.metadata.get("slippage_guard_triggered"):
            market_fit_reasons.append("slippage_guard_triggered")
            market_fit_status = "slippage_guard_triggered"
            market_fit_score = min(market_fit_score, 0.25 if market_fit_score > 0 else 0.0)
        if self.partial_fill and "partial_fill" not in market_fit_reasons:
            market_fit_reasons.append("partial_fill")
        self.market_fit_status = market_fit_status
        self.market_fit_score = round(max(0.0, min(1.0, market_fit_score)), 6)
        self.shadow_eligible = self.market_fit_status in {"fit", "partial_fit", "synthetic_reference"}
        self.market_fit_reasons = list(dict.fromkeys(market_fit_reasons))
        return self

    def to_execution_metadata(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "request_id": self.request_id,
            "run_id": self.run_id,
            "market_id": self.market_id,
            "venue": self.venue.value,
            "position_side": self.position_side.value,
            "execution_side": self.execution_side.value,
            "status": self.status.value,
            "reference_price": self.reference_price,
            "average_fill_price": self.average_fill_price,
            "top_of_book_price": self.top_of_book_price,
            "spread_mean_bps": self.spread_mean_bps,
            "spread_bps": self.spread_bps,
            "slippage_bps": self.slippage_bps,
            "closing_line_drift_bps": self.closing_line_drift_bps,
            "fill_ratio": self.fill_ratio,
            "partial_fill": self.partial_fill,
            "synthetic_reference": self.synthetic_reference,
            "limit_price": self.limit_price,
            "liquidity_available_quantity": self.liquidity_available_quantity,
            "liquidity_available_notional": self.liquidity_available_notional,
            "liquidity_consumed_fraction": self.liquidity_consumed_fraction,
            "fill_count": self.fill_count,
            "average_fill_quantity": self.average_fill_quantity,
            "fragmented": self.fragmented,
            "fragmentation_score": self.fragmentation_score,
            "market_fit_status": self.market_fit_status,
            "market_fit_score": self.market_fit_score,
            "shadow_eligible": self.shadow_eligible,
            "market_fit_reasons": list(self.market_fit_reasons),
            "gross_cash_flow": self.gross_cash_flow,
            "net_cash_flow": self.net_cash_flow,
            "effective_price_after_fees": self.effective_price_after_fees,
            "fee_paid": self.fee_paid,
            "no_trade_reasons": list(self.no_trade_reasons),
            "metadata": dict(self.metadata),
        }

    def postmortem(self) -> "SlippageLiquidityPostmortem":
        notes = []
        if self.status == SlippageLiquidityStatus.filled:
            notes.append("filled")
        elif self.status == SlippageLiquidityStatus.partial:
            notes.append("partial_fill")
        elif self.status == SlippageLiquidityStatus.no_liquidity:
            notes.append("no_liquidity")
        elif self.status == SlippageLiquidityStatus.synthetic:
            notes.append("synthetic_reference")
        elif self.status == SlippageLiquidityStatus.rejected:
            notes.append("rejected")
        if self.metadata.get("slippage_guard_triggered"):
            notes.append("slippage_guard_triggered")
        if self.partial_fill:
            notes.append("partial_fill_detected")
        if self.fragmented:
            notes.append("fragmented_execution")
        recommendation = "hold"
        if self.status in {SlippageLiquidityStatus.no_liquidity, SlippageLiquidityStatus.rejected}:
            recommendation = "wait"
        elif self.partial_fill:
            recommendation = "reduce_size"
        elif abs(self.closing_line_drift_bps) > 100.0:
            recommendation = "reprice"
        return SlippageLiquidityPostmortem(
            report_id=self.report_id,
            request_id=self.request_id,
            run_id=self.run_id,
            market_id=self.market_id,
            venue=self.venue,
            status=self.status,
            fill_rate=self.fill_ratio,
            reference_price=self.reference_price,
            average_fill_price=self.average_fill_price,
            closing_line_drift_bps=self.closing_line_drift_bps,
            slippage_bps=self.slippage_bps,
            fee_paid=self.fee_paid,
            recommendation=recommendation,
            notes=notes,
            metadata=dict(self.metadata),
        )


class SlippageLiquidityPostmortem(BaseModel):
    schema_version: str = "v1"
    postmortem_id: str = Field(default_factory=lambda: f"slippm_{uuid4().hex[:12]}")
    report_id: str
    request_id: str
    run_id: str
    market_id: str
    venue: VenueName = VenueName.polymarket
    status: SlippageLiquidityStatus = SlippageLiquidityStatus.no_liquidity
    fill_rate: float = 0.0
    reference_price: float = 0.0
    average_fill_price: float | None = None
    closing_line_drift_bps: float = 0.0
    slippage_bps: float = 0.0
    fee_paid: float = 0.0
    recommendation: str = "hold"
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class SlippageLiquiditySimulator:
    fee_bps: float = 0.0
    max_slippage_bps: float | None = None
    min_depth_near_touch: float = 0.0

    def simulate(
        self,
        snapshot: MarketSnapshot,
        *,
        position_side: TradeSide,
        execution_side: TradeSide = TradeSide.buy,
        requested_quantity: float | None = None,
        requested_notional: float | None = None,
        limit_price: float | None = None,
        run_id: str | None = None,
        market_id: str | None = None,
        venue: VenueName | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SlippageLiquidityReport:
        request = SlippageLiquidityRequest(
            run_id=run_id,
            market_id=market_id or snapshot.market_id,
            venue=venue or snapshot.venue,
            snapshot_id=snapshot.snapshot_id,
            position_side=position_side,
            execution_side=execution_side,
            requested_quantity=requested_quantity,
            requested_notional=requested_notional,
            limit_price=limit_price,
            fee_bps=self.fee_bps,
            metadata=metadata or {},
        )
        return self.simulate_request(snapshot, request)

    def simulate_request(self, snapshot: MarketSnapshot, request: SlippageLiquidityRequest) -> SlippageLiquidityReport:
        reference_price = _reference_price(snapshot, request.position_side)
        min_depth_near_touch = max(0.0, float(self.min_depth_near_touch))
        requested_quantity, requested_notional = _normalize_request_amounts(
            requested_quantity=request.requested_quantity,
            requested_notional=request.requested_notional,
            reference_price=reference_price,
        )
        run_id = request.run_id or f"slippage_{uuid4().hex[:12]}"
        market_id = request.market_id or snapshot.market_id
        venue = request.venue or snapshot.venue

        if min_depth_near_touch > 0.0 and snapshot.depth_near_touch is not None and snapshot.depth_near_touch < min_depth_near_touch:
            return self._build_report(
                request=request,
                run_id=run_id,
                market_id=market_id,
                venue=venue,
                snapshot=snapshot,
                reference_price=reference_price,
                requested_quantity=requested_quantity,
                requested_notional=requested_notional,
                fills=[],
                curve=[],
                status=SlippageLiquidityStatus.no_liquidity,
                synthetic_reference=False,
                limit_price=request.limit_price,
                liquidity_available_quantity=0.0,
                liquidity_available_notional=0.0,
                no_trade_reasons=[
                    f"depth_near_touch_below_minimum:{snapshot.depth_near_touch:.2f}/{min_depth_near_touch:.2f}",
                ],
                top_of_book_price=round(float(snapshot.price_yes or reference_price), 6),
            )

        if requested_quantity <= 0:
            return SlippageLiquidityReport(
                request_id=request.request_id,
                run_id=run_id,
                market_id=market_id,
                venue=venue,
                snapshot_id=request.snapshot_id or snapshot.snapshot_id,
                position_side=request.position_side,
                execution_side=request.execution_side,
                status=SlippageLiquidityStatus.rejected,
                requested_quantity=0.0,
                requested_notional=0.0,
                reference_price=reference_price,
                limit_price=request.limit_price,
                no_trade_reasons=["requested_quantity_must_be_positive"],
                metadata=_merge_metadata({"fee_bps": self.fee_bps, "request": request.metadata}, request.metadata),
            )

        levels = list(_levels_for_side(snapshot, position_side=request.position_side, execution_side=request.execution_side))
        curve: list[SlippageLiquidityCurvePoint] = []
        fills: list[SlippageLiquidityFill] = []

        if not levels:
            fill = _synthetic_fill(
                market_id=market_id,
                venue=venue,
                position_side=request.position_side,
                execution_side=request.execution_side,
                requested_quantity=requested_quantity,
                reference_price=reference_price,
                request_id=request.request_id,
                run_id=run_id,
                metadata={"source": "synthetic_reference", **request.metadata},
            )
            fills = [fill]
            curve = [
                SlippageLiquidityCurvePoint(
                    market_id=market_id,
                    venue=venue,
                    position_side=request.position_side,
                    execution_side=request.execution_side,
                    level_index=0,
                    level_price=reference_price,
                    level_quantity=requested_quantity,
                    cumulative_quantity=requested_quantity,
                    cumulative_notional=round(requested_quantity * reference_price, 6),
                    average_fill_price=reference_price,
                    marginal_slippage_bps=0.0,
                    remaining_quantity=0.0,
                    metadata={"source": "synthetic_reference"},
                )
            ]
            return self._build_report(
                request=request,
                run_id=run_id,
                market_id=market_id,
                venue=venue,
                snapshot=snapshot,
                reference_price=reference_price,
                requested_quantity=requested_quantity,
                requested_notional=requested_notional,
                fills=fills,
                curve=curve,
                status=SlippageLiquidityStatus.synthetic,
                synthetic_reference=True,
                limit_price=request.limit_price,
                liquidity_available_quantity=requested_quantity,
                liquidity_available_notional=requested_quantity * reference_price,
            )

        remaining = requested_quantity
        cumulative_quantity = 0.0
        cumulative_notional = 0.0
        liquidity_available_quantity = 0.0
        liquidity_available_notional = 0.0
        matched_any_level = False
        top_of_book_price = round(float(levels[0].price), 6) if levels else reference_price

        for level_index, level in enumerate(levels):
            if level.size <= 0:
                continue
            if request.limit_price is not None and not _within_limit(level.price, request.execution_side, request.limit_price):
                break

            liquidity_available_quantity += float(level.size)
            liquidity_available_notional += float(level.size) * float(level.price)

            fill_qty = min(remaining, max(0.0, float(level.size)))
            if fill_qty <= 0:
                continue

            matched_any_level = True
            notional = fill_qty * float(level.price)
            cumulative_quantity += fill_qty
            cumulative_notional += notional
            remaining = max(0.0, requested_quantity - cumulative_quantity)

            fill = SlippageLiquidityFill(
                market_id=market_id,
                venue=venue,
                position_side=request.position_side,
                execution_side=request.execution_side,
                level_index=level_index,
                source="orderbook",
                requested_quantity=requested_quantity,
                filled_quantity=fill_qty,
                fill_price=float(level.price),
                gross_notional=notional,
                cumulative_quantity=cumulative_quantity,
                cumulative_notional=cumulative_notional,
                marginal_slippage_bps=_signed_slippage_bps(reference_price, float(level.price), request.execution_side),
                signed_slippage_bps=_signed_slippage_bps(reference_price, float(level.price), request.execution_side),
                metadata=dict(getattr(level, "metadata", {}) or {}),
            )
            fills.append(fill)
            curve.append(
                SlippageLiquidityCurvePoint(
                    market_id=market_id,
                    venue=venue,
                    position_side=request.position_side,
                    execution_side=request.execution_side,
                    level_index=level_index,
                    level_price=float(level.price),
                    level_quantity=float(fill_qty),
                    cumulative_quantity=cumulative_quantity,
                    cumulative_notional=cumulative_notional,
                    average_fill_price=round(cumulative_notional / cumulative_quantity, 6),
                    marginal_slippage_bps=_signed_slippage_bps(reference_price, float(level.price), request.execution_side),
                    remaining_quantity=remaining,
                    metadata=dict(getattr(level, "metadata", {}) or {}),
                )
            )

            if remaining <= 1e-12:
                break

        if not matched_any_level:
            return self._build_report(
                request=request,
                run_id=run_id,
                market_id=market_id,
                venue=venue,
                snapshot=snapshot,
                reference_price=reference_price,
                requested_quantity=requested_quantity,
                requested_notional=requested_notional,
                fills=[],
                curve=[],
                status=SlippageLiquidityStatus.no_liquidity,
                synthetic_reference=False,
                limit_price=request.limit_price,
                liquidity_available_quantity=liquidity_available_quantity,
                liquidity_available_notional=liquidity_available_notional,
                no_trade_reasons=["limit_price_excludes_orderbook" if request.limit_price is not None else "no_matching_liquidity"],
                top_of_book_price=top_of_book_price,
            )

        status = SlippageLiquidityStatus.filled if remaining <= 1e-12 else SlippageLiquidityStatus.partial
        return self._build_report(
            request=request,
            run_id=run_id,
            market_id=market_id,
            venue=venue,
            snapshot=snapshot,
            reference_price=reference_price,
            requested_quantity=requested_quantity,
            requested_notional=requested_notional,
            fills=fills,
            curve=curve,
            status=status,
            synthetic_reference=False,
            limit_price=request.limit_price,
            liquidity_available_quantity=liquidity_available_quantity,
            liquidity_available_notional=liquidity_available_notional,
            top_of_book_price=top_of_book_price,
        )

    def estimate_capacity(
        self,
        snapshot: MarketSnapshot,
        *,
        position_side: TradeSide,
        execution_side: TradeSide = TradeSide.buy,
        limit_price: float | None = None,
    ) -> dict[str, float | bool | None]:
        levels = list(_levels_for_side(snapshot, position_side=position_side, execution_side=execution_side))
        reference_price = _reference_price(snapshot, position_side)
        quantity = 0.0
        notional = 0.0
        top_of_book_price = round(float(levels[0].price), 6) if levels else reference_price
        for level in levels:
            if level.size <= 0:
                continue
            if limit_price is not None and not _within_limit(level.price, execution_side, limit_price):
                break
            quantity += float(level.size)
            notional += float(level.size) * float(level.price)
        return {
            "market_id": snapshot.market_id,
            "venue": snapshot.venue.value,
            "position_side": position_side.value,
            "execution_side": execution_side.value,
            "reference_price": reference_price,
            "top_of_book_price": top_of_book_price,
            "liquidity_available_quantity": round(quantity, 6),
            "liquidity_available_notional": round(notional, 6),
            "has_orderbook": bool(snapshot.orderbook),
            "limit_price": limit_price,
        }

    def _build_report(
        self,
        *,
        request: SlippageLiquidityRequest,
        run_id: str,
        market_id: str,
        venue: VenueName,
        snapshot: MarketSnapshot,
        reference_price: float,
        requested_quantity: float,
        requested_notional: float,
        fills: list[SlippageLiquidityFill],
        curve: list[SlippageLiquidityCurvePoint],
        status: SlippageLiquidityStatus,
        synthetic_reference: bool,
        limit_price: float | None,
        liquidity_available_quantity: float,
        liquidity_available_notional: float,
        no_trade_reasons: list[str] | None = None,
        top_of_book_price: float | None = None,
    ) -> SlippageLiquidityReport:
        filled_quantity = sum(fill.filled_quantity for fill in fills)
        filled_notional = sum(fill.gross_notional for fill in fills)
        average_fill_price = filled_notional / filled_quantity if filled_quantity > 0 else None
        best_fill_price = min((fill.fill_price for fill in fills), default=None)
        worst_fill_price = max((fill.fill_price for fill in fills), default=None)
        fee_paid = filled_notional * (self.fee_bps / 10000.0)
        slippage_bps = 0.0
        if average_fill_price is not None:
            slippage_bps = _signed_slippage_bps(reference_price, average_fill_price, request.execution_side)
        spread_bps = snapshot.spread_bps
        closing_line_drift_bps = slippage_bps
        liquidity_consumed_fraction = 0.0
        if liquidity_available_quantity > 0:
            liquidity_consumed_fraction = round(min(1.0, filled_quantity / liquidity_available_quantity), 6)

        report = SlippageLiquidityReport(
            request_id=request.request_id,
            run_id=run_id,
            market_id=market_id,
            venue=venue,
            snapshot_id=request.snapshot_id or snapshot.snapshot_id,
            position_side=request.position_side,
            execution_side=request.execution_side,
            status=status,
            requested_quantity=requested_quantity,
            requested_notional=requested_notional,
            filled_quantity=filled_quantity,
            filled_notional=filled_notional,
            remaining_quantity=max(0.0, requested_quantity - filled_quantity),
            fill_ratio=0.0 if requested_quantity <= 0 else min(1.0, filled_quantity / requested_quantity),
            reference_price=reference_price,
            top_of_book_price=top_of_book_price,
            spread_mean_bps=spread_bps,
            average_fill_price=average_fill_price,
            best_fill_price=best_fill_price,
            worst_fill_price=worst_fill_price,
            spread_bps=spread_bps,
            slippage_bps=slippage_bps,
            closing_line_drift_bps=closing_line_drift_bps,
            fee_paid=fee_paid,
            liquidity_available_quantity=liquidity_available_quantity,
            liquidity_available_notional=liquidity_available_notional,
            liquidity_consumed_fraction=liquidity_consumed_fraction,
            synthetic_reference=synthetic_reference,
            partial_fill=status == SlippageLiquidityStatus.partial,
            limit_price=limit_price,
            no_trade_reasons=list(no_trade_reasons or []),
            fills=fills,
            curve=curve,
            metadata={
                "fee_bps": self.fee_bps,
                "max_slippage_bps": self.max_slippage_bps,
                "min_depth_near_touch": self.min_depth_near_touch,
                "snapshot_status": snapshot.status.value,
                **request.metadata,
            },
        )
        if self.max_slippage_bps is not None and abs(report.slippage_bps) > self.max_slippage_bps:
            report.metadata["slippage_guard_triggered"] = True
        return report


def simulate_slippage_liquidity(
    snapshot: MarketSnapshot,
    *,
    position_side: TradeSide,
    execution_side: TradeSide = TradeSide.buy,
    requested_quantity: float | None = None,
    requested_notional: float | None = None,
    limit_price: float | None = None,
    run_id: str | None = None,
    market_id: str | None = None,
    venue: VenueName | None = None,
    fee_bps: float = 0.0,
    metadata: dict[str, Any] | None = None,
) -> SlippageLiquidityReport:
    return SlippageLiquiditySimulator(fee_bps=fee_bps).simulate(
        snapshot,
        position_side=position_side,
        execution_side=execution_side,
        requested_quantity=requested_quantity,
        requested_notional=requested_notional,
        limit_price=limit_price,
        run_id=run_id,
        market_id=market_id,
        venue=venue,
        metadata=metadata,
    )


def _reference_price(snapshot: MarketSnapshot, position_side: TradeSide) -> float:
    yes_price = snapshot.price_yes or snapshot.midpoint_yes or snapshot.market_implied_probability or 0.5
    yes_price = max(1e-6, min(1.0 - 1e-6, float(yes_price)))
    if position_side == TradeSide.no:
        return round(max(1e-6, min(1.0 - 1e-6, 1.0 - yes_price)), 6)
    return round(yes_price, 6)


def _normalize_request_amounts(
    *,
    requested_quantity: float | None,
    requested_notional: float | None,
    reference_price: float,
) -> tuple[float, float]:
    if requested_quantity is None and requested_notional is None:
        return 0.0, 0.0
    if requested_quantity is None and requested_notional is not None:
        requested_quantity = requested_notional / max(reference_price, 1e-9)
    if requested_notional is None and requested_quantity is not None:
        requested_notional = requested_quantity * reference_price
    return max(0.0, float(requested_quantity or 0.0)), max(0.0, float(requested_notional or 0.0))


def _levels_for_side(
    snapshot: MarketSnapshot,
    *,
    position_side: TradeSide,
    execution_side: TradeSide,
) -> Iterable[Any]:
    orderbook = snapshot.orderbook
    if orderbook is None:
        return []
    if position_side == TradeSide.yes and execution_side == TradeSide.buy:
        return sorted(orderbook.asks, key=lambda level: level.price)
    if position_side == TradeSide.yes and execution_side == TradeSide.sell:
        return sorted(orderbook.bids, key=lambda level: level.price, reverse=True)
    if position_side == TradeSide.no and execution_side == TradeSide.buy:
        return [_mirror_level(level, inverse=True) for level in sorted(orderbook.bids, key=lambda level: level.price, reverse=True)]
    if position_side == TradeSide.no and execution_side == TradeSide.sell:
        return [_mirror_level(level, inverse=True) for level in sorted(orderbook.asks, key=lambda level: level.price)]
    return []


def _mirror_level(level: Any, *, inverse: bool = False) -> Any:
    price = 1.0 - float(level.price) if inverse else float(level.price)
    price = round(max(0.0, min(1.0, price)), 6)
    return type(level)(price=price, size=float(level.size), metadata=dict(getattr(level, "metadata", {}) or {}))


def _within_limit(price: float, execution_side: TradeSide, limit_price: float) -> bool:
    if execution_side == TradeSide.buy:
        return price <= limit_price + 1e-12
    return price >= limit_price - 1e-12


def _signed_slippage_bps(reference_price: float, fill_price: float, execution_side: TradeSide) -> float:
    raw = (float(fill_price) - float(reference_price)) * 10000.0
    if execution_side == TradeSide.sell:
        raw = -raw
    return round(raw, 2)


def _synthetic_fill(
    *,
    market_id: str,
    venue: VenueName,
    position_side: TradeSide,
    execution_side: TradeSide,
    requested_quantity: float,
    reference_price: float,
    request_id: str,
    run_id: str,
    metadata: dict[str, Any] | None = None,
) -> SlippageLiquidityFill:
    notional = requested_quantity * reference_price
    return SlippageLiquidityFill(
        market_id=market_id,
        venue=venue,
        position_side=position_side,
        execution_side=execution_side,
        level_index=0,
        source="synthetic_reference",
        requested_quantity=requested_quantity,
        filled_quantity=requested_quantity,
        fill_price=reference_price,
        gross_notional=notional,
        cumulative_quantity=requested_quantity,
        cumulative_notional=notional,
        marginal_slippage_bps=0.0,
        signed_slippage_bps=0.0,
        metadata={"request_id": request_id, "run_id": run_id, **(metadata or {})},
    )


def _merge_metadata(*payloads: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for payload in payloads:
        merged.update(payload)
    return merged
