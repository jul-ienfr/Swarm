from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import MarketOrderBook, MarketSnapshot, OrderBookLevel, TradeSide, VenueName


class MicrostructureStatus(str, Enum):
    filled = "filled"
    partial = "partial"
    queue_miss = "queue_miss"
    spread_collapse = "spread_collapse"
    capital_locked = "capital_locked"
    rejected = "rejected"
    synthetic = "synthetic"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clamp_unit_interval(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _mirror_price(price: float) -> float:
    return round(max(0.0, min(1.0, 1.0 - float(price))), 6)


def _normalize_price(level: OrderBookLevel, position_side: TradeSide) -> float:
    if position_side == TradeSide.no:
        return _mirror_price(level.price)
    return round(_clamp_unit_interval(level.price), 6)


class MicrostructureFill(BaseModel):
    schema_version: str = "v1"
    fill_id: str = Field(default_factory=lambda: f"msfill_{uuid4().hex[:12]}")
    level_index: int
    source: str = "orderbook"
    requested_quantity: float = 0.0
    filled_quantity: float = 0.0
    fill_price: float = 0.0
    gross_notional: float = 0.0
    cumulative_quantity: float = 0.0
    cumulative_notional: float = 0.0
    queue_ahead_quantity: float = 0.0
    capital_remaining_usd: float | None = None
    metadata: dict[str, float | str | int | bool] = Field(default_factory=dict)

    @field_validator(
        "requested_quantity",
        "filled_quantity",
        "fill_price",
        "gross_notional",
        "cumulative_quantity",
        "cumulative_notional",
        "queue_ahead_quantity",
    )
    @classmethod
    def _non_negative(cls, value: float) -> float:
        return max(0.0, float(value))


class MicrostructureCurvePoint(BaseModel):
    schema_version: str = "v1"
    point_id: str = Field(default_factory=lambda: f"mscurve_{uuid4().hex[:12]}")
    level_index: int
    level_price: float
    level_quantity: float
    accessible_quantity: float
    requested_remaining_before: float
    filled_quantity: float
    cumulative_quantity: float
    cumulative_notional: float
    remaining_quantity: float
    queue_ahead_quantity: float = 0.0
    collapse_factor: float = 1.0
    capital_remaining_usd: float | None = None
    metadata: dict[str, float | str | int | bool] = Field(default_factory=dict)

    @field_validator(
        "level_price",
        "level_quantity",
        "accessible_quantity",
        "requested_remaining_before",
        "filled_quantity",
        "cumulative_quantity",
        "cumulative_notional",
        "remaining_quantity",
        "queue_ahead_quantity",
        "collapse_factor",
    )
    @classmethod
    def _normalize(cls, value: float) -> float:
        return max(0.0, float(value))


class MicrostructureScenario(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "v1"
    scenario_id: str = Field(default_factory=lambda: f"msscn_{uuid4().hex[:12]}")
    snapshot: MarketSnapshot
    position_side: TradeSide = TradeSide.yes
    execution_side: TradeSide = TradeSide.buy
    requested_quantity: float = 0.0
    capital_available_usd: float | None = None
    capital_locked_usd: float = 0.0
    queue_ahead_quantity: float = 0.0
    spread_collapse_threshold_bps: float = 50.0
    collapse_liquidity_multiplier: float = 0.35
    limit_price: float | None = None
    fee_bps: float = 0.0
    metadata: dict[str, float | str | int | bool] = Field(default_factory=dict)

    @field_validator("requested_quantity", "capital_available_usd", "capital_locked_usd", "queue_ahead_quantity", "spread_collapse_threshold_bps", "collapse_liquidity_multiplier", "fee_bps", "limit_price", mode="before")
    @classmethod
    def _normalize_numeric(cls, value):  # noqa: ANN001
        if value is None:
            return None
        return float(value)

    @model_validator(mode="after")
    def _normalize(self) -> "MicrostructureScenario":
        self.requested_quantity = max(0.0, float(self.requested_quantity))
        self.capital_available_usd = None if self.capital_available_usd is None else max(0.0, float(self.capital_available_usd))
        self.capital_locked_usd = max(0.0, float(self.capital_locked_usd))
        self.queue_ahead_quantity = max(0.0, float(self.queue_ahead_quantity))
        self.spread_collapse_threshold_bps = max(0.0, float(self.spread_collapse_threshold_bps))
        self.collapse_liquidity_multiplier = _clamp_unit_interval(self.collapse_liquidity_multiplier)
        self.fee_bps = max(0.0, float(self.fee_bps))
        if self.limit_price is not None:
            self.limit_price = _clamp_unit_interval(self.limit_price)
        return self


class MicrostructureReport(BaseModel):
    schema_version: str = "v1"
    report_id: str = Field(default_factory=lambda: f"msrpt_{uuid4().hex[:12]}")
    scenario_id: str
    market_id: str
    venue: VenueName
    snapshot_id: str
    status: MicrostructureStatus = MicrostructureStatus.rejected
    requested_quantity: float = 0.0
    filled_quantity: float = 0.0
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
    fee_paid: float = 0.0
    capital_available_usd: float | None = None
    capital_locked_usd: float = 0.0
    capital_budget_usd: float | None = None
    capital_locked: bool = False
    queue_miss: bool = False
    spread_collapse: bool = False
    partial_fill: bool = False
    synthetic_reference: bool = False
    market_fit_status: str = "unknown"
    market_fit_score: float = 0.0
    shadow_eligible: bool = False
    market_fit_reasons: list[str] = Field(default_factory=list)
    fill_count: int = 0
    no_trade_reasons: list[str] = Field(default_factory=list)
    fills: list[MicrostructureFill] = Field(default_factory=list)
    curve: list[MicrostructureCurvePoint] = Field(default_factory=list)
    metadata: dict[str, float | str | int | bool] = Field(default_factory=dict)

    @field_validator(
        "requested_quantity",
        "filled_quantity",
        "remaining_quantity",
        "fill_ratio",
        "reference_price",
        "top_of_book_price",
        "average_fill_price",
        "best_fill_price",
        "worst_fill_price",
        "spread_bps",
        "slippage_bps",
        "fee_paid",
        "capital_available_usd",
        "capital_locked_usd",
        "capital_budget_usd",
    )
    @classmethod
    def _normalize_numeric(cls, value):  # noqa: ANN001
        if value is None:
            return None
        return float(value)

    @model_validator(mode="after")
    def _derive(self) -> "MicrostructureReport":
        self.fill_count = len(self.fills)
        self.remaining_quantity = max(0.0, self.requested_quantity - self.filled_quantity)
        if self.requested_quantity > 0 and self.fill_ratio == 0.0:
            self.fill_ratio = round(min(1.0, self.filled_quantity / self.requested_quantity), 6)
        if self.fill_count > 0 and self.average_fill_price is None:
            total = sum(fill.filled_quantity * fill.fill_price for fill in self.fills)
            qty = sum(fill.filled_quantity for fill in self.fills)
            self.average_fill_price = round(total / qty, 6) if qty > 0 else None
        if self.fills and self.best_fill_price is None:
            self.best_fill_price = min(fill.fill_price for fill in self.fills)
        if self.fills and self.worst_fill_price is None:
            self.worst_fill_price = max(fill.fill_price for fill in self.fills)
        self.partial_fill = self.filled_quantity > 0 and self.remaining_quantity > 0
        if self.capital_available_usd is not None and self.capital_budget_usd is None:
            self.capital_budget_usd = max(0.0, float(self.capital_available_usd) - float(self.capital_locked_usd))
        if self.capital_budget_usd is not None:
            self.capital_locked = self.capital_locked or self.capital_budget_usd <= 0.0
        if self.filled_quantity > 0 and self.average_fill_price is not None:
            self.slippage_bps = round(max(0.0, (self.average_fill_price - self.reference_price) / max(self.reference_price, 1e-9) * 10_000.0), 2)
        if self.requested_quantity > 0 and self.filled_quantity == 0:
            self.fill_ratio = 0.0
        market_fit_reasons: list[str] = []
        if self.queue_miss:
            market_fit_status = "queue_miss"
            market_fit_score = 0.0
            market_fit_reasons.append("queue_miss")
        elif self.spread_collapse:
            market_fit_status = "spread_collapse"
            market_fit_score = 0.0
            market_fit_reasons.append("spread_collapse")
        elif self.capital_locked:
            market_fit_status = "capital_locked"
            market_fit_score = 0.0
            market_fit_reasons.append("capital_locked")
        elif self.status == MicrostructureStatus.filled:
            market_fit_status = "fit"
            market_fit_score = 1.0
        elif self.status == MicrostructureStatus.partial:
            market_fit_status = "partial_fit"
            market_fit_score = round(min(1.0, max(0.0, self.fill_ratio)), 6)
            market_fit_reasons.append("partial_fill")
        elif self.status == MicrostructureStatus.synthetic:
            market_fit_status = "synthetic_reference"
            market_fit_score = 0.75
            market_fit_reasons.append("synthetic_reference")
        else:
            market_fit_status = "rejected"
            market_fit_score = 0.0
            market_fit_reasons.append("rejected")
        if self.no_trade_reasons:
            market_fit_reasons.extend(self.no_trade_reasons)
        if self.partial_fill and "partial_fill" not in market_fit_reasons:
            market_fit_reasons.append("partial_fill")
        self.market_fit_status = market_fit_status
        self.market_fit_score = round(max(0.0, min(1.0, market_fit_score)), 6)
        self.shadow_eligible = self.market_fit_status in {"fit", "partial_fit", "synthetic_reference"}
        self.market_fit_reasons = list(dict.fromkeys(market_fit_reasons))
        return self

    def to_execution_metadata(self) -> dict[str, float | str | int | bool | list[str]]:
        return {
            "report_id": self.report_id,
            "scenario_id": self.scenario_id,
            "market_id": self.market_id,
            "venue": self.venue.value,
            "status": self.status.value,
            "requested_quantity": self.requested_quantity,
            "filled_quantity": self.filled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "fill_ratio": self.fill_ratio,
            "reference_price": self.reference_price,
            "top_of_book_price": self.top_of_book_price,
            "spread_mean_bps": self.spread_mean_bps,
            "average_fill_price": self.average_fill_price,
            "slippage_bps": self.slippage_bps,
            "fee_paid": self.fee_paid,
            "capital_available_usd": self.capital_available_usd,
            "capital_locked_usd": self.capital_locked_usd,
            "capital_budget_usd": self.capital_budget_usd,
            "capital_locked": self.capital_locked,
            "queue_miss": self.queue_miss,
            "spread_collapse": self.spread_collapse,
            "partial_fill": self.partial_fill,
            "synthetic_reference": self.synthetic_reference,
            "market_fit_status": self.market_fit_status,
            "market_fit_score": self.market_fit_score,
            "shadow_eligible": self.shadow_eligible,
            "market_fit_reasons": list(self.market_fit_reasons),
            "fill_count": self.fill_count,
            "no_trade_reasons": list(self.no_trade_reasons),
        }

    def postmortem(self) -> "MicrostructurePostmortem":
        notes = []
        if self.status == MicrostructureStatus.filled:
            notes.append("filled")
        elif self.status == MicrostructureStatus.partial:
            notes.append("partial_fill")
        elif self.status == MicrostructureStatus.queue_miss:
            notes.append("queue_miss")
        elif self.status == MicrostructureStatus.spread_collapse:
            notes.append("spread_collapse")
        elif self.status == MicrostructureStatus.capital_locked:
            notes.append("capital_locked")
        elif self.status == MicrostructureStatus.synthetic:
            notes.append("synthetic_reference")
        elif self.status == MicrostructureStatus.rejected:
            notes.append("rejected")
        if self.partial_fill:
            notes.append("partial_fill_detected")
        if self.queue_miss:
            notes.append("queue_miss_detected")
        if self.spread_collapse:
            notes.append("spread_collapse_detected")
        if self.capital_locked:
            notes.append("capital_locked_detected")
        if self.synthetic_reference:
            notes.append("synthetic_reference")

        recommendation = "hold"
        if self.status in {MicrostructureStatus.queue_miss, MicrostructureStatus.capital_locked, MicrostructureStatus.rejected}:
            recommendation = "wait"
        elif self.status == MicrostructureStatus.spread_collapse:
            recommendation = "reprice"
        elif self.partial_fill:
            recommendation = "reduce_size"

        return MicrostructurePostmortem(
            report_id=self.report_id,
            scenario_id=self.scenario_id,
            market_id=self.market_id,
            venue=self.venue,
            snapshot_id=self.snapshot_id,
            status=self.status,
            requested_quantity=self.requested_quantity,
            filled_quantity=self.filled_quantity,
            fill_rate=self.fill_ratio,
            reference_price=self.reference_price,
            average_fill_price=self.average_fill_price,
            spread_bps=self.spread_bps,
            slippage_bps=self.slippage_bps,
            fee_paid=self.fee_paid,
            fill_count=self.fill_count,
            partial_fill=self.partial_fill,
            queue_miss=self.queue_miss,
            spread_collapse=self.spread_collapse,
            capital_locked=self.capital_locked,
            synthetic_reference=self.synthetic_reference,
            recommendation=recommendation,
            notes=notes,
            metadata=dict(self.metadata),
        )


class MicrostructurePostmortem(BaseModel):
    schema_version: str = "v1"
    postmortem_id: str = Field(default_factory=lambda: f"mspm_{uuid4().hex[:12]}")
    report_id: str
    scenario_id: str
    market_id: str
    venue: VenueName = VenueName.polymarket
    snapshot_id: str
    status: MicrostructureStatus = MicrostructureStatus.rejected
    requested_quantity: float = 0.0
    filled_quantity: float = 0.0
    fill_rate: float = 0.0
    reference_price: float = 0.0
    average_fill_price: float | None = None
    spread_bps: float | None = None
    slippage_bps: float = 0.0
    fee_paid: float = 0.0
    fill_count: int = 0
    partial_fill: bool = False
    queue_miss: bool = False
    spread_collapse: bool = False
    capital_locked: bool = False
    synthetic_reference: bool = False
    recommendation: str = "hold"
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, float | str | int | bool] = Field(default_factory=dict)


class MicrostructureLab:
    def simulate(
        self,
        scenario: MicrostructureScenario | MarketSnapshot | None = None,
        *,
        snapshot: MarketSnapshot | None = None,
        position_side: TradeSide = TradeSide.yes,
        execution_side: TradeSide = TradeSide.buy,
        requested_quantity: float = 0.0,
        capital_available_usd: float | None = None,
        capital_locked_usd: float = 0.0,
        queue_ahead_quantity: float = 0.0,
        spread_collapse_threshold_bps: float = 50.0,
        collapse_liquidity_multiplier: float = 0.35,
        limit_price: float | None = None,
        fee_bps: float = 0.0,
        metadata: dict[str, float | str | int | bool] | None = None,
    ) -> MicrostructureReport:
        if isinstance(scenario, MicrostructureScenario):
            scenario_obj = scenario
        else:
            snapshot_obj = snapshot or scenario
            if not isinstance(snapshot_obj, MarketSnapshot):
                raise TypeError("simulate() requires a MicrostructureScenario or a MarketSnapshot")
            scenario_obj = MicrostructureScenario(
                snapshot=snapshot_obj,
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
                metadata=metadata or {},
            )

        snapshot = scenario_obj.snapshot
        orderbook = snapshot.orderbook
        reference_price = _reference_price(snapshot, scenario_obj.position_side)

        if scenario_obj.requested_quantity <= 0:
            return MicrostructureReport(
                scenario_id=scenario_obj.scenario_id,
                market_id=snapshot.market_id,
                venue=snapshot.venue,
                snapshot_id=snapshot.snapshot_id,
                status=MicrostructureStatus.rejected,
                requested_quantity=0.0,
                filled_quantity=0.0,
                reference_price=reference_price,
                spread_bps=snapshot.spread_bps,
                spread_mean_bps=snapshot.spread_bps,
                no_trade_reasons=["requested_quantity_non_positive"],
                metadata=dict(scenario_obj.metadata),
            )

        capital_budget = None
        if scenario_obj.capital_available_usd is not None:
            capital_budget = max(0.0, float(scenario_obj.capital_available_usd) - float(scenario_obj.capital_locked_usd))
            if capital_budget <= 0.0:
                return MicrostructureReport(
                    scenario_id=scenario_obj.scenario_id,
                    market_id=snapshot.market_id,
                    venue=snapshot.venue,
                    snapshot_id=snapshot.snapshot_id,
                    status=MicrostructureStatus.capital_locked,
                    requested_quantity=scenario_obj.requested_quantity,
                    filled_quantity=0.0,
                    reference_price=reference_price,
                    spread_bps=snapshot.spread_bps,
                    spread_mean_bps=snapshot.spread_bps,
                    capital_available_usd=scenario_obj.capital_available_usd,
                    capital_locked_usd=scenario_obj.capital_locked_usd,
                    capital_budget_usd=capital_budget,
                    capital_locked=True,
                    no_trade_reasons=["capital_locked"],
                    metadata=dict(scenario_obj.metadata),
                )

        if orderbook is None:
            return self._synthetic_report(snapshot, scenario_obj, reference_price)

        levels = _levels_for_scenario(orderbook, scenario_obj.position_side, scenario_obj.execution_side)
        if not levels:
            return self._synthetic_report(snapshot, scenario_obj, reference_price)

        spread_collapse = snapshot.spread_bps is not None and snapshot.spread_bps <= scenario_obj.spread_collapse_threshold_bps
        queue_miss = False
        fills: list[MicrostructureFill] = []
        curve: list[MicrostructureCurvePoint] = []
        filled_quantity = 0.0
        filled_notional = 0.0
        remaining_quantity = scenario_obj.requested_quantity
        capital_remaining = capital_budget
        no_trade_reasons: list[str] = []
        top_of_book_price = levels[0][0]

        for level_index, (level_price, level_quantity, source) in enumerate(levels):
            accessible_quantity = level_quantity
            queue_ahead_quantity = scenario_obj.queue_ahead_quantity if level_index == 0 else 0.0
            if level_index == 0 and scenario_obj.queue_ahead_quantity > 0:
                queue_miss = True
                accessible_quantity = max(0.0, accessible_quantity - scenario_obj.queue_ahead_quantity)
            collapse_factor = 1.0
            if spread_collapse:
                collapse_factor = scenario_obj.collapse_liquidity_multiplier
                accessible_quantity *= collapse_factor
            if scenario_obj.limit_price is not None:
                if scenario_obj.execution_side == TradeSide.buy and level_price > scenario_obj.limit_price:
                    no_trade_reasons.append("limit_price_excludes_orderbook")
                    accessible_quantity = 0.0
                elif scenario_obj.execution_side == TradeSide.sell and level_price < scenario_obj.limit_price:
                    no_trade_reasons.append("limit_price_excludes_orderbook")
                    accessible_quantity = 0.0
            if capital_remaining is not None:
                accessible_quantity = min(accessible_quantity, capital_remaining / max(level_price, 1e-9))
            if accessible_quantity <= 0:
                curve.append(
                    MicrostructureCurvePoint(
                        level_index=level_index,
                        level_price=level_price,
                        level_quantity=level_quantity,
                        accessible_quantity=0.0,
                        requested_remaining_before=remaining_quantity,
                        filled_quantity=0.0,
                        cumulative_quantity=filled_quantity,
                        cumulative_notional=filled_notional,
                        remaining_quantity=remaining_quantity,
                        queue_ahead_quantity=queue_ahead_quantity,
                        collapse_factor=collapse_factor,
                        capital_remaining_usd=capital_remaining,
                        metadata={"source": source},
                    )
                )
                continue

            level_fill = min(remaining_quantity, accessible_quantity)
            level_notional = round(level_fill * level_price, 6)
            filled_quantity = round(filled_quantity + level_fill, 6)
            filled_notional = round(filled_notional + level_notional, 6)
            remaining_quantity = round(max(0.0, scenario_obj.requested_quantity - filled_quantity), 6)
            if capital_remaining is not None:
                capital_remaining = round(max(0.0, capital_remaining - level_notional), 6)

            fills.append(
                MicrostructureFill(
                    level_index=level_index,
                    source=source,
                    requested_quantity=scenario_obj.requested_quantity,
                    filled_quantity=level_fill,
                    fill_price=level_price,
                    gross_notional=level_notional,
                    cumulative_quantity=filled_quantity,
                    cumulative_notional=filled_notional,
                    queue_ahead_quantity=queue_ahead_quantity,
                    capital_remaining_usd=capital_remaining,
                    metadata={"spread_collapse": spread_collapse},
                )
            )
            curve.append(
                MicrostructureCurvePoint(
                    level_index=level_index,
                    level_price=level_price,
                    level_quantity=level_quantity,
                    accessible_quantity=accessible_quantity,
                    requested_remaining_before=max(0.0, scenario_obj.requested_quantity - (filled_quantity - level_fill)),
                    filled_quantity=level_fill,
                    cumulative_quantity=filled_quantity,
                    cumulative_notional=filled_notional,
                    remaining_quantity=remaining_quantity,
                    queue_ahead_quantity=queue_ahead_quantity,
                    collapse_factor=collapse_factor,
                    capital_remaining_usd=capital_remaining,
                    metadata={"source": source},
                )
            )

            if remaining_quantity <= 0:
                break
            if capital_remaining is not None and capital_remaining <= 0:
                break

        filled = filled_quantity > 0
        capital_locked = capital_remaining is not None and capital_remaining <= 0 and remaining_quantity > 0
        status = MicrostructureStatus.filled
        if not filled:
            if capital_budget is not None and capital_budget <= 0:
                status = MicrostructureStatus.capital_locked
            elif queue_miss:
                status = MicrostructureStatus.queue_miss
            elif spread_collapse:
                status = MicrostructureStatus.spread_collapse
            elif no_trade_reasons:
                status = MicrostructureStatus.rejected
            else:
                status = MicrostructureStatus.rejected
        elif remaining_quantity > 0:
            if capital_locked:
                status = MicrostructureStatus.capital_locked
            elif spread_collapse:
                status = MicrostructureStatus.spread_collapse
            elif queue_miss:
                status = MicrostructureStatus.partial
            else:
                status = MicrostructureStatus.partial
        elif spread_collapse:
            status = MicrostructureStatus.spread_collapse

        average_fill_price = round(filled_notional / filled_quantity, 6) if filled_quantity > 0 else None
        slippage_bps = 0.0
        if average_fill_price is not None and reference_price > 0:
            slippage_bps = round(max(0.0, (average_fill_price - reference_price) / reference_price * 10_000.0), 2)

        if capital_locked and "capital_locked" not in no_trade_reasons:
            no_trade_reasons.append("capital_locked")
        if queue_miss and "queue_miss" not in no_trade_reasons:
            no_trade_reasons.append("queue_miss")
        if spread_collapse and "spread_collapse" not in no_trade_reasons:
            no_trade_reasons.append("spread_collapse")

        return MicrostructureReport(
            scenario_id=scenario_obj.scenario_id,
            market_id=snapshot.market_id,
            venue=snapshot.venue,
            snapshot_id=snapshot.snapshot_id,
            status=status,
            requested_quantity=scenario_obj.requested_quantity,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
            fill_ratio=0.0 if scenario_obj.requested_quantity <= 0 else round(min(1.0, filled_quantity / scenario_obj.requested_quantity), 6),
            reference_price=reference_price,
            top_of_book_price=top_of_book_price,
            spread_mean_bps=snapshot.spread_bps,
            average_fill_price=average_fill_price,
            spread_bps=snapshot.spread_bps,
            slippage_bps=slippage_bps,
            capital_available_usd=scenario_obj.capital_available_usd,
            capital_locked_usd=scenario_obj.capital_locked_usd,
            capital_budget_usd=capital_remaining,
            capital_locked=capital_locked,
            queue_miss=queue_miss,
            spread_collapse=spread_collapse,
            partial_fill=remaining_quantity > 0 and filled_quantity > 0,
            synthetic_reference=False,
            fee_paid=round(filled_notional * scenario_obj.fee_bps / 10_000.0, 6),
            no_trade_reasons=no_trade_reasons,
            fills=fills,
            curve=curve,
            metadata=dict(scenario_obj.metadata),
        )

    def _synthetic_report(
        self,
        snapshot: MarketSnapshot,
        scenario: MicrostructureScenario,
        reference_price: float,
    ) -> MicrostructureReport:
        filled_notional = round(scenario.requested_quantity * reference_price, 6)
        fill = MicrostructureFill(
            level_index=0,
            source="synthetic_reference",
            requested_quantity=scenario.requested_quantity,
            filled_quantity=scenario.requested_quantity,
            fill_price=reference_price,
            gross_notional=filled_notional,
            cumulative_quantity=scenario.requested_quantity,
            cumulative_notional=filled_notional,
            queue_ahead_quantity=0.0,
            capital_remaining_usd=None if scenario.capital_available_usd is None else max(
                0.0, float(scenario.capital_available_usd) - filled_notional
            ),
            metadata={"synthetic_reference": True},
        )
        curve = [
            MicrostructureCurvePoint(
                level_index=0,
                level_price=reference_price,
                level_quantity=scenario.requested_quantity,
                accessible_quantity=scenario.requested_quantity,
                requested_remaining_before=scenario.requested_quantity,
                filled_quantity=scenario.requested_quantity,
                cumulative_quantity=scenario.requested_quantity,
                cumulative_notional=filled_notional,
                remaining_quantity=0.0,
                queue_ahead_quantity=0.0,
                collapse_factor=1.0,
                capital_remaining_usd=fill.capital_remaining_usd,
                metadata={"synthetic_reference": True},
            )
        ]
        return MicrostructureReport(
            scenario_id=scenario.scenario_id,
            market_id=snapshot.market_id,
            venue=snapshot.venue,
            snapshot_id=snapshot.snapshot_id,
            status=MicrostructureStatus.synthetic,
            requested_quantity=scenario.requested_quantity,
            filled_quantity=scenario.requested_quantity,
            remaining_quantity=0.0,
            fill_ratio=1.0,
            reference_price=reference_price,
            top_of_book_price=reference_price,
            spread_mean_bps=snapshot.spread_bps,
            average_fill_price=reference_price,
            best_fill_price=reference_price,
            worst_fill_price=reference_price,
            spread_bps=snapshot.spread_bps,
            slippage_bps=0.0,
            fee_paid=round(filled_notional * scenario.fee_bps / 10_000.0, 6),
            capital_available_usd=scenario.capital_available_usd,
            capital_locked_usd=scenario.capital_locked_usd,
            capital_budget_usd=None if scenario.capital_available_usd is None else max(
                0.0, float(scenario.capital_available_usd) - float(scenario.capital_locked_usd)
            ),
            capital_locked=False,
            queue_miss=False,
            spread_collapse=False,
            partial_fill=False,
            synthetic_reference=True,
            fills=[fill],
            curve=curve,
            metadata=dict(scenario.metadata),
        )


def simulate_microstructure_lab(
    snapshot: MarketSnapshot,
    *,
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
    metadata: dict[str, float | str | int | bool] | None = None,
) -> MicrostructureReport:
    scenario = MicrostructureScenario(
        snapshot=snapshot,
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
        metadata=metadata or {},
    )
    return MicrostructureLab().simulate(scenario)


def _reference_price(snapshot: MarketSnapshot, position_side: TradeSide) -> float:
    base = snapshot.mid_probability
    if base is None:
        base = snapshot.price_yes
    if base is None and snapshot.best_bid_yes is not None and snapshot.best_ask_yes is not None:
        base = (snapshot.best_bid_yes + snapshot.best_ask_yes) / 2.0
    if base is None:
        base = 0.5
    if position_side == TradeSide.no:
        return _mirror_price(base)
    return round(_clamp_unit_interval(base), 6)


def _levels_for_scenario(
    orderbook: MarketOrderBook,
    position_side: TradeSide,
    execution_side: TradeSide,
) -> list[tuple[float, float, str]]:
    if execution_side not in {TradeSide.buy, TradeSide.sell}:
        raise ValueError("execution_side must be buy or sell")
    if position_side not in {TradeSide.yes, TradeSide.no}:
        raise ValueError("position_side must be yes or no")

    if position_side == TradeSide.yes:
        if execution_side == TradeSide.buy:
            raw_levels = sorted(orderbook.asks, key=lambda level: float(level.price))
        else:
            raw_levels = sorted(orderbook.bids, key=lambda level: float(level.price), reverse=True)
        source = "orderbook"
        return [(_clamp_unit_interval(level.price), max(0.0, float(level.size)), source) for level in raw_levels]

    if execution_side == TradeSide.buy:
        raw_levels = sorted(orderbook.bids, key=lambda level: float(level.price), reverse=True)
    else:
        raw_levels = sorted(orderbook.asks, key=lambda level: float(level.price))
    source = "mirrored_orderbook"
    return [(_mirror_price(level.price), max(0.0, float(level.size)), source) for level in raw_levels]
