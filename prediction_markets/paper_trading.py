from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from .models import DecisionAction, MarketOrderBook, MarketSnapshot, PaperTradeRecord, TradeSide, VenueName
from .paths import PredictionMarketPaths, default_prediction_market_paths
from .storage import save_json


class PaperTradeStatus(str, Enum):
    filled = "filled"
    partial = "partial"
    skipped = "skipped"
    rejected = "rejected"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PaperTradeFill(BaseModel):
    schema_version: str = "v1"
    fill_id: str = Field(default_factory=lambda: f"fill_{uuid4().hex[:12]}")
    trade_id: str
    run_id: str
    market_id: str
    venue: VenueName
    position_side: TradeSide
    execution_side: TradeSide
    requested_quantity: float
    filled_quantity: float
    fill_price: float
    gross_notional: float
    fee_paid: float = 0.0
    slippage_bps: float = 0.0
    level_index: int | None = None
    timestamp: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("requested_quantity", "filled_quantity", "fill_price", "gross_notional", "fee_paid")
    @classmethod
    def _clamp_non_negative(cls, value: float) -> float:
        return max(0.0, float(value))


class PaperTradeSimulation(BaseModel):
    schema_version: str = "v1"
    trade_id: str = Field(default_factory=lambda: f"paper_{uuid4().hex[:12]}")
    run_id: str
    market_id: str
    venue: VenueName = VenueName.polymarket
    action: DecisionAction = DecisionAction.bet
    position_side: TradeSide = TradeSide.yes
    execution_side: TradeSide = TradeSide.buy
    stake: float = 0.0
    requested_quantity: float = 0.0
    filled_quantity: float = 0.0
    average_fill_price: float | None = None
    reference_price: float | None = None
    gross_notional: float = 0.0
    fee_paid: float = 0.0
    cash_flow: float = 0.0
    slippage_bps: float = 0.0
    order_count: int = 1
    fill_count: int = 0
    settlement_status: str = "simulated"
    status: PaperTradeStatus = PaperTradeStatus.skipped
    snapshot_id: str | None = None
    fills: list[PaperTradeFill] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("stake", "requested_quantity", "filled_quantity", "gross_notional", "fee_paid", "cash_flow")
    @classmethod
    def _clamp_non_negative(cls, value: float) -> float:
        return float(value)

    @model_validator(mode="after")
    def _derive_average_price(self) -> "PaperTradeSimulation":
        self.fill_count = len(self.fills) if self.fill_count <= 0 else max(0, int(self.fill_count))
        self.order_count = max(1, int(self.order_count))
        if not self.settlement_status:
            self.settlement_status = "simulated"
        if self.status in {PaperTradeStatus.filled, PaperTradeStatus.partial}:
            if self.settlement_status == "simulated":
                self.settlement_status = "simulated_settled"
        else:
            if self.settlement_status == "simulated":
                self.settlement_status = "not_settled"
        if self.filled_quantity > 0 and self.average_fill_price is None:
            self.average_fill_price = round(self.gross_notional / self.filled_quantity, 6)
        if self.average_fill_price is not None:
            self.average_fill_price = round(max(0.0, min(1.0, float(self.average_fill_price))), 6)
        return self

    @property
    def is_active(self) -> bool:
        return self.status in {PaperTradeStatus.filled, PaperTradeStatus.partial}

    def to_paper_trade_record(self) -> PaperTradeRecord:
        return PaperTradeRecord(
            trade_id=self.trade_id,
            run_id=self.run_id,
            venue=self.venue,
            market_id=self.market_id,
            action=self.action,
            side=self.position_side,
            size=self.stake,
            entry_price=self.average_fill_price if self.average_fill_price is not None else self.reference_price,
            status=self.status.value,
            metadata=dict(self.metadata),
        )

    def postmortem(self) -> "PaperTradePostmortem":
        fill_rate = 0.0 if self.requested_quantity <= 0 else round(min(1.0, self.filled_quantity / self.requested_quantity), 6)
        closing_line_drift_bps = 0.0
        if self.average_fill_price is not None and self.reference_price is not None:
            closing_line_drift_bps = round((self.average_fill_price - self.reference_price) * 10000.0, 2)
        fill_count = len(self.fills)
        average_fill_quantity = 0.0 if fill_count <= 0 else round(self.filled_quantity / fill_count, 6)
        fragmented = fill_count > 1
        fragmentation_score = 0.0
        if fragmented and self.filled_quantity > 0:
            largest_fill = max(fill.filled_quantity for fill in self.fills)
            fragmentation_score = round(1.0 - min(1.0, largest_fill / self.filled_quantity), 6)
        gross_cash_flow = self.gross_notional if self.execution_side == TradeSide.sell else -self.gross_notional
        net_cash_flow = gross_cash_flow - self.fee_paid
        effective_price_after_fees = None
        if self.filled_quantity > 0:
            effective_price_after_fees = round(abs(net_cash_flow) / self.filled_quantity, 6)
        stale_blocked = bool(self.metadata.get("stale_blocked")) or str(self.metadata.get("reason", "")) == "snapshot_stale"
        slippage_guard_triggered = bool(self.metadata.get("slippage_guard_triggered"))
        no_trade_zone = (
            bool(self.metadata.get("no_trade_zone"))
            or self.status in {PaperTradeStatus.skipped, PaperTradeStatus.rejected}
            or stale_blocked
            or slippage_guard_triggered
        )
        notes = []
        if self.status is PaperTradeStatus.filled:
            notes.append("filled")
        elif self.status is PaperTradeStatus.partial:
            notes.append("partial_fill")
        elif self.status is PaperTradeStatus.skipped:
            notes.append("skipped")
        elif self.status is PaperTradeStatus.rejected:
            notes.append("rejected")
        if slippage_guard_triggered:
            notes.append("slippage_guard_triggered")
        if fragmented:
            notes.append("fragmented")
        if no_trade_zone:
            notes.append("no_trade_zone")
        if stale_blocked:
            notes.append("stale_blocked")
        if no_trade_zone and self.status in {PaperTradeStatus.filled, PaperTradeStatus.partial}:
            notes.append("reclassified_no_trade")
        if self.metadata.get("reason"):
            notes.append(str(self.metadata["reason"]))
        recommendation = "hold"
        if no_trade_zone:
            recommendation = "no_trade"
        elif self.status in {PaperTradeStatus.skipped, PaperTradeStatus.rejected}:
            recommendation = "review_thresholds"
        elif self.status is PaperTradeStatus.partial:
            recommendation = "reduce_size"
        elif abs(closing_line_drift_bps) > 100.0:
            recommendation = "reprice"
        return PaperTradePostmortem(
            run_id=self.run_id,
            trade_id=self.trade_id,
            market_id=self.market_id,
            venue=self.venue,
            status=self.status,
            position_side=self.position_side,
            execution_side=self.execution_side,
            order_count=self.order_count,
            requested_quantity=self.requested_quantity,
            filled_quantity=self.filled_quantity,
            fill_rate=fill_rate,
            reference_price=self.reference_price,
            average_fill_price=self.average_fill_price,
            closing_line_drift_bps=closing_line_drift_bps,
            slippage_bps=self.slippage_bps,
            fee_paid=self.fee_paid,
            fee_bps=float(self.metadata.get("fee_bps", 0.0) or 0.0),
            gross_notional=self.gross_notional,
            gross_cash_flow=gross_cash_flow,
            net_cash_flow=net_cash_flow,
            balance_delta_usd=net_cash_flow,
            effective_price_after_fees=effective_price_after_fees,
            fill_count=fill_count,
            average_fill_quantity=average_fill_quantity,
            fragmented=fragmented,
            fragmentation_score=fragmentation_score,
            no_trade_zone=no_trade_zone,
            stale_blocked=stale_blocked,
            settlement_status=self.settlement_status,
            recommendation=recommendation,
            notes=notes,
            metadata=dict(self.metadata),
        )


class PaperTradePostmortem(BaseModel):
    schema_version: str = "v1"
    postmortem_id: str = Field(default_factory=lambda: f"paperpm_{uuid4().hex[:12]}")
    run_id: str
    trade_id: str
    market_id: str
    venue: VenueName = VenueName.polymarket
    status: PaperTradeStatus = PaperTradeStatus.skipped
    position_side: TradeSide
    execution_side: TradeSide
    order_count: int = 1
    requested_quantity: float = 0.0
    filled_quantity: float = 0.0
    fill_rate: float = 0.0
    reference_price: float | None = None
    average_fill_price: float | None = None
    closing_line_drift_bps: float = 0.0
    slippage_bps: float = 0.0
    fee_paid: float = 0.0
    fee_bps: float = 0.0
    gross_notional: float = 0.0
    gross_cash_flow: float = 0.0
    net_cash_flow: float = 0.0
    balance_delta_usd: float = 0.0
    effective_price_after_fees: float | None = None
    fill_count: int = 0
    average_fill_quantity: float = 0.0
    fragmented: bool = False
    fragmentation_score: float = 0.0
    no_trade_zone: bool = False
    stale_blocked: bool = False
    settlement_status: str = "not_settled"
    recommendation: str = "hold"
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaperTradeSurface(BaseModel):
    schema_version: str = "v1"
    report_id: str | None = None
    trade_count: int = 0
    order_count: int = 0
    fill_count: int = 0
    filled_trade_count: int = 0
    partial_trade_count: int = 0
    skipped_trade_count: int = 0
    rejected_trade_count: int = 0
    no_trade_zone_count: int = 0
    stale_block_count: int = 0
    settled_trade_count: int = 0
    total_requested_quantity: float = 0.0
    total_filled_quantity: float = 0.0
    fee_paid_usd: float = 0.0
    cash_flow_usd: float = 0.0
    fill_rate: float = 0.0
    partial_fill_rate: float = 0.0
    no_trade_zone_rate: float = 0.0
    stale_block_rate: float = 0.0
    reject_rate: float = 0.0
    settlement_rate: float = 0.0
    average_slippage_bps: float = 0.0
    spread_mean_bps: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_simulations(
        cls,
        simulations: Iterable[PaperTradeSimulation],
        *,
        report_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "PaperTradeSurface":
        items = [simulation.model_copy() for simulation in simulations]
        postmortems = [item.postmortem() for item in items]
        trade_count = len(items)
        order_count = trade_count
        fill_count = sum(len(item.fills) for item in items)
        filled_trade_count = sum(1 for item in items if item.status is PaperTradeStatus.filled)
        partial_trade_count = sum(1 for item in items if item.status is PaperTradeStatus.partial)
        skipped_trade_count = sum(1 for item in items if item.status is PaperTradeStatus.skipped)
        rejected_trade_count = sum(1 for item in items if item.status is PaperTradeStatus.rejected)
        no_trade_zone_count = sum(1 for item in postmortems if item.no_trade_zone)
        stale_block_count = sum(1 for item in postmortems if item.stale_blocked)
        settled_trade_count = sum(1 for item in postmortems if item.settlement_status == "simulated_settled")
        total_requested_quantity = sum(max(0.0, float(item.requested_quantity)) for item in items)
        total_filled_quantity = sum(max(0.0, float(item.filled_quantity)) for item in items)
        fee_paid_usd = sum(max(0.0, float(item.fee_paid)) for item in items)
        cash_flow_usd = sum(float(item.cash_flow) for item in items)
        fill_rate = 0.0 if total_requested_quantity <= 0.0 else round(total_filled_quantity / total_requested_quantity, 6)
        partial_fill_rate = 0.0 if trade_count <= 0 else round(partial_trade_count / trade_count, 6)
        no_trade_zone_rate = 0.0 if trade_count <= 0 else round(no_trade_zone_count / trade_count, 6)
        stale_block_rate = 0.0 if trade_count <= 0 else round(stale_block_count / trade_count, 6)
        reject_rate = 0.0 if trade_count <= 0 else round(rejected_trade_count / trade_count, 6)
        settlement_rate = 0.0 if trade_count <= 0 else round(settled_trade_count / trade_count, 6)
        slippage_weight = 0.0
        slippage_weight_denominator = 0.0
        spread_values: list[float] = []
        for item in items:
            if item.filled_quantity > 0:
                slippage_weight += abs(float(item.slippage_bps)) * float(item.filled_quantity)
                slippage_weight_denominator += float(item.filled_quantity)
            spread_bps = item.metadata.get("spread_bps")
            if spread_bps is not None:
                spread_values.append(float(spread_bps))
        average_slippage_bps = 0.0 if slippage_weight_denominator <= 0.0 else round(slippage_weight / slippage_weight_denominator, 2)
        spread_mean_bps = None if not spread_values else round(sum(spread_values) / len(spread_values), 2)
        return cls(
            report_id=report_id,
            trade_count=trade_count,
            order_count=order_count,
            fill_count=fill_count,
            filled_trade_count=filled_trade_count,
            partial_trade_count=partial_trade_count,
            skipped_trade_count=skipped_trade_count,
            rejected_trade_count=rejected_trade_count,
            no_trade_zone_count=no_trade_zone_count,
            stale_block_count=stale_block_count,
            settled_trade_count=settled_trade_count,
            total_requested_quantity=round(total_requested_quantity, 6),
            total_filled_quantity=round(total_filled_quantity, 6),
            fee_paid_usd=round(fee_paid_usd, 6),
            cash_flow_usd=round(cash_flow_usd, 6),
            fill_rate=fill_rate,
            partial_fill_rate=partial_fill_rate,
            no_trade_zone_rate=no_trade_zone_rate,
            stale_block_rate=stale_block_rate,
            reject_rate=reject_rate,
            settlement_rate=settlement_rate,
            average_slippage_bps=average_slippage_bps,
            spread_mean_bps=spread_mean_bps,
            metadata={
                **dict(metadata or {}),
                "filled_trade_count": filled_trade_count,
                "partial_trade_count": partial_trade_count,
                "no_trade_zone_count": no_trade_zone_count,
                "no_trade_zone_rate": no_trade_zone_rate,
                "stale_block_count": stale_block_count,
                "settled_trade_count": settled_trade_count,
                "fee_paid_usd": round(fee_paid_usd, 6),
                "cash_flow_usd": round(cash_flow_usd, 6),
                "reject_rate": reject_rate,
                "settlement_rate": settlement_rate,
                "average_slippage_bps": average_slippage_bps,
                "spread_mean_bps": spread_mean_bps,
            },
        )


class PaperTradeReport(BaseModel):
    schema_version: str = "v1"
    report_id: str = Field(default_factory=lambda: f"paprpt_{uuid4().hex[:12]}")
    simulations: list[PaperTradeSimulation] = Field(default_factory=list)
    surface: PaperTradeSurface = Field(default_factory=PaperTradeSurface)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "PaperTradeReport":
        self.simulations = [simulation.model_copy() for simulation in self.simulations]
        self.surface = PaperTradeSurface.from_simulations(self.simulations, report_id=self.report_id, metadata=self.metadata)
        if not self.content_hash:
            from .models import _stable_content_hash

            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        return self

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "PaperTradeReport":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class PaperTradeStore:
    def __init__(self, paths: PredictionMarketPaths | None = None, *, base_dir: str | Path | None = None) -> None:
        if paths is not None:
            self.paths = paths
        elif base_dir is not None:
            self.paths = PredictionMarketPaths(Path(base_dir))
        else:
            self.paths = default_prediction_market_paths()
        self.paths.ensure_layout()
        self.root = self.paths.paper_trades_dir
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, simulation: PaperTradeSimulation) -> Path:
        path = self.root / f"{simulation.trade_id}.json"
        save_json(path, simulation)
        return path

    def load(self, trade_id: str) -> PaperTradeSimulation:
        return PaperTradeSimulation.model_validate_json((self.root / f"{trade_id}.json").read_text(encoding="utf-8"))

    def list(self) -> list[PaperTradeSimulation]:
        if not self.root.exists():
            return []
        records: list[PaperTradeSimulation] = []
        for path in sorted(self.root.glob("*.json")):
            records.append(PaperTradeSimulation.model_validate_json(path.read_text(encoding="utf-8")))
        return records


@dataclass
class PaperTradeSimulator:
    fee_bps: float = 25.0
    max_slippage_bps: float = 250.0
    max_snapshot_staleness_ms: int = 120_000

    def simulate(
        self,
        snapshot: MarketSnapshot,
        *,
        position_side: TradeSide,
        execution_side: TradeSide = TradeSide.buy,
        stake: float = 10.0,
        run_id: str | None = None,
        market_id: str | None = None,
        venue: VenueName | None = None,
        limit_price: float | None = None,
        action: DecisionAction = DecisionAction.bet,
        metadata: dict[str, Any] | None = None,
    ) -> PaperTradeSimulation:
        if position_side not in {TradeSide.yes, TradeSide.no}:
            raise ValueError("position_side must be yes or no.")
        if execution_side not in {TradeSide.buy, TradeSide.sell}:
            raise ValueError("execution_side must be buy or sell.")
        if stake <= 0:
            trade_id = run_id or f"paper_{uuid4().hex[:12]}"
            return PaperTradeSimulation(
                trade_id=trade_id,
                run_id=trade_id,
                market_id=market_id or snapshot.market_id,
                venue=venue or snapshot.venue,
                action=action,
                position_side=position_side,
                execution_side=execution_side,
                stake=stake,
                status=PaperTradeStatus.rejected,
                metadata={"reason": "stake must be positive", "no_trade_zone": True, "spread_bps": snapshot.spread_bps, **(metadata or {})},
            )

        if snapshot.staleness_ms is not None and snapshot.staleness_ms > self.max_snapshot_staleness_ms:
            trade_id = run_id or f"paper_{uuid4().hex[:12]}"
            reference_price = _reference_price(snapshot, position_side)
            requested_quantity = round(stake / max(reference_price, 1e-9), 8)
            return PaperTradeSimulation(
                trade_id=trade_id,
                run_id=trade_id,
                market_id=market_id or snapshot.market_id,
                venue=venue or snapshot.venue,
                action=action,
                position_side=position_side,
                execution_side=execution_side,
                stake=stake,
                requested_quantity=requested_quantity,
                reference_price=reference_price,
                snapshot_id=snapshot.snapshot_id,
                status=PaperTradeStatus.skipped,
                metadata={
                    "reason": "snapshot_stale",
                    "no_trade_zone": True,
                    "stale_blocked": True,
                    "snapshot_staleness_ms": snapshot.staleness_ms,
                    "spread_bps": snapshot.spread_bps,
                    **(metadata or {}),
                },
            )

        reference_price = _reference_price(snapshot, position_side)
        requested_quantity = round(stake / max(reference_price, 1e-9), 8)
        trade_id = run_id or f"paper_{uuid4().hex[:12]}"
        fills, filled_quantity, gross_notional = self._match_against_book(
            snapshot,
            position_side=position_side,
            execution_side=execution_side,
            requested_quantity=requested_quantity,
            limit_price=limit_price,
            run_id=trade_id,
            trade_id=trade_id,
        )
        if filled_quantity <= 0:
            return PaperTradeSimulation(
                trade_id=trade_id,
                run_id=trade_id,
                market_id=market_id or snapshot.market_id,
                venue=venue or snapshot.venue,
                action=action,
                position_side=position_side,
                execution_side=execution_side,
                stake=stake,
                requested_quantity=requested_quantity,
                reference_price=reference_price,
                snapshot_id=snapshot.snapshot_id,
                status=PaperTradeStatus.skipped,
                metadata={"reason": "no liquidity matched", "no_trade_zone": True, "spread_bps": snapshot.spread_bps, **(metadata or {})},
            )

        average_fill_price = gross_notional / filled_quantity
        fee_paid = gross_notional * (self.fee_bps / 10000.0)
        cash_flow = gross_notional if execution_side == TradeSide.sell else -gross_notional
        slippage_bps = _signed_slippage_bps(reference_price, average_fill_price, execution_side)
        status = PaperTradeStatus.filled if filled_quantity >= requested_quantity - 1e-9 else PaperTradeStatus.partial
        simulation = PaperTradeSimulation(
            trade_id=trade_id,
            run_id=trade_id,
            market_id=market_id or snapshot.market_id,
            venue=venue or snapshot.venue,
            action=action,
            position_side=position_side,
            execution_side=execution_side,
            stake=stake,
            requested_quantity=requested_quantity,
            filled_quantity=filled_quantity,
            average_fill_price=average_fill_price,
            reference_price=reference_price,
            gross_notional=gross_notional,
            fee_paid=fee_paid,
            cash_flow=cash_flow - fee_paid if execution_side == TradeSide.sell else cash_flow - fee_paid,
            slippage_bps=slippage_bps,
            status=status,
            snapshot_id=snapshot.snapshot_id,
            fills=fills,
            metadata={
                "fee_bps": self.fee_bps,
                "limit_price": limit_price,
                "max_slippage_bps": self.max_slippage_bps,
                "fill_count": len(fills),
                "spread_bps": snapshot.spread_bps,
                **(metadata or {}),
            },
        )
        if abs(simulation.slippage_bps) > self.max_slippage_bps:
            simulation.metadata["slippage_guard_triggered"] = True
        return simulation

    def simulate_from_recommendation(
        self,
        snapshot: MarketSnapshot,
        *,
        recommendation_action: DecisionAction,
        side: TradeSide | None,
        stake: float = 10.0,
        run_id: str | None = None,
        limit_price: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PaperTradeSimulation:
        if recommendation_action != DecisionAction.bet or side not in {TradeSide.yes, TradeSide.no}:
            return PaperTradeSimulation(
                run_id=run_id or f"paper_{uuid4().hex[:12]}",
                market_id=snapshot.market_id,
                venue=snapshot.venue,
                action=recommendation_action,
                position_side=TradeSide.yes if side is None else side,
                execution_side=TradeSide.buy,
                stake=stake,
                reference_price=_reference_price(snapshot, side or TradeSide.yes),
                snapshot_id=snapshot.snapshot_id,
                status=PaperTradeStatus.skipped,
                metadata={
                    "reason": "recommendation does not call for a bet",
                    "no_trade_zone": True,
                    "recommendation_action": recommendation_action.value,
                    "spread_bps": snapshot.spread_bps,
                    **(metadata or {}),
                },
            )
        return self.simulate(
            snapshot,
            position_side=side,
            execution_side=TradeSide.buy,
            stake=stake,
            run_id=run_id,
            limit_price=limit_price,
            action=recommendation_action,
            metadata=metadata,
        )

    def persist(self, simulation: PaperTradeSimulation, store: PaperTradeStore | None = None) -> Path:
        store = store or PaperTradeStore()
        return store.save(simulation)

    def _match_against_book(
        self,
        snapshot: MarketSnapshot,
        *,
        position_side: TradeSide,
        execution_side: TradeSide,
        requested_quantity: float,
        limit_price: float | None,
        run_id: str,
        trade_id: str,
    ) -> tuple[list[PaperTradeFill], float, float]:
        levels = list(_levels_for_side(snapshot, position_side=position_side, execution_side=execution_side))
        if not levels:
            reference = _reference_price(snapshot, position_side)
            fill = PaperTradeFill(
                trade_id=trade_id,
                run_id=run_id,
                market_id=snapshot.market_id,
                venue=snapshot.venue,
                position_side=position_side,
                execution_side=execution_side,
                requested_quantity=requested_quantity,
                filled_quantity=requested_quantity,
                fill_price=reference,
                gross_notional=requested_quantity * reference,
                fee_paid=(requested_quantity * reference) * (self.fee_bps / 10000.0),
                slippage_bps=0.0,
                level_index=0,
                metadata={"source": "synthetic_reference"},
            )
            return [fill], requested_quantity, fill.gross_notional

        remaining = requested_quantity
        fills: list[PaperTradeFill] = []
        gross_notional = 0.0
        for level_index, level in enumerate(levels):
            if remaining <= 1e-12:
                break
            if limit_price is not None:
                if execution_side == TradeSide.buy and level.price > limit_price + 1e-12:
                    break
                if execution_side == TradeSide.sell and level.price < limit_price - 1e-12:
                    break
            fill_qty = min(remaining, max(0.0, level.size))
            if fill_qty <= 0:
                continue
            notional = fill_qty * level.price
            fee_paid = notional * (self.fee_bps / 10000.0)
            fill = PaperTradeFill(
                trade_id=trade_id,
                run_id=run_id,
                market_id=snapshot.market_id,
                venue=snapshot.venue,
                position_side=position_side,
                execution_side=execution_side,
                requested_quantity=requested_quantity,
                filled_quantity=fill_qty,
                fill_price=level.price,
                gross_notional=notional,
                fee_paid=fee_paid,
                slippage_bps=0.0,
                level_index=level_index,
                metadata=dict(level.metadata),
            )
            fills.append(fill)
            gross_notional += notional
            remaining -= fill_qty

        filled_quantity = requested_quantity - remaining
        for fill in fills:
            fill.slippage_bps = _signed_slippage_bps(
                _reference_price(snapshot, position_side),
                fill.fill_price,
                execution_side,
            )
        return fills, filled_quantity, gross_notional


def _reference_price(snapshot: MarketSnapshot, position_side: TradeSide) -> float:
    yes_price = snapshot.price_yes or snapshot.midpoint_yes or snapshot.market_implied_probability or 0.5
    yes_price = max(1e-6, min(1.0 - 1e-6, float(yes_price)))
    if position_side == TradeSide.no:
        return round(max(1e-6, min(1.0 - 1e-6, 1.0 - yes_price)), 6)
    return round(yes_price, 6)


def _levels_for_side(
    snapshot: MarketSnapshot,
    *,
    position_side: TradeSide,
    execution_side: TradeSide,
) -> Iterable[MarketOrderBook | Any]:
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
    return type(level)(price=price, size=float(level.size), metadata=dict(getattr(level, "metadata", {}) or {}))


def _signed_slippage_bps(reference_price: float, fill_price: float, execution_side: TradeSide) -> float:
    raw = (float(fill_price) - float(reference_price)) * 10000.0
    if execution_side == TradeSide.sell:
        raw = -raw
    return round(raw, 2)


def build_paper_trade_report(
    simulations: Iterable[PaperTradeSimulation],
    *,
    metadata: dict[str, Any] | None = None,
) -> PaperTradeReport:
    return PaperTradeReport(
        simulations=list(simulations),
        metadata=dict(metadata or {}),
    )
