from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class PaperTradeStatus(str, Enum):
    filled = "filled"
    partial = "partial"
    skipped = "skipped"
    rejected = "rejected"


class PaperPositionSide(str, Enum):
    yes = "yes"
    no = "no"


class PaperExecutionSide(str, Enum):
    buy = "buy"
    sell = "sell"


class PaperTradeFill(BaseModel):
    schema_version: str = "v1"
    fill_id: str = Field(default_factory=lambda: f"fill_{uuid4().hex[:12]}")
    trade_id: str
    run_id: str
    market_id: str
    position_side: PaperPositionSide = PaperPositionSide.yes
    execution_side: PaperExecutionSide = PaperExecutionSide.buy
    requested_quantity: float
    filled_quantity: float
    fill_price: float
    gross_notional: float
    fee_paid: float = 0.0
    slippage_bps: float = 0.0
    level_index: int | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaperTradeSimulation(BaseModel):
    schema_version: str = "v1"
    trade_id: str = Field(default_factory=lambda: f"paper_{uuid4().hex[:12]}")
    run_id: str
    market_id: str
    position_side: PaperPositionSide = PaperPositionSide.yes
    execution_side: PaperExecutionSide = PaperExecutionSide.buy
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _derive_fields(self) -> "PaperTradeSimulation":
        self.fill_count = len(self.fills) if self.fill_count <= 0 else max(0, int(self.fill_count))
        self.order_count = max(1, int(self.order_count))
        if not self.settlement_status:
            self.settlement_status = "simulated"
        if self.status in {PaperTradeStatus.filled, PaperTradeStatus.partial}:
            if self.settlement_status == "simulated":
                self.settlement_status = "simulated_settled"
        elif self.settlement_status == "simulated":
            self.settlement_status = "not_settled"
        if self.filled_quantity > 0 and self.average_fill_price is None:
            self.average_fill_price = round(self.gross_notional / self.filled_quantity, 6)
        if self.average_fill_price is not None:
            self.average_fill_price = round(max(0.0, min(1.0, float(self.average_fill_price))), 6)
        return self

    @property
    def is_active(self) -> bool:
        return self.status in {PaperTradeStatus.filled, PaperTradeStatus.partial}
