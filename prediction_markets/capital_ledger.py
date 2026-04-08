from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from pydantic import BaseModel, Field

from .models import CapitalLedgerSnapshot, LedgerPosition, PaperTradeRecord, TradeSide, VenueName
from .paper_trading import PaperTradeSimulation
from .paths import PredictionMarketPaths, default_prediction_market_paths
from .storage import save_json


def _resolve_captured_at(metadata: Mapping[str, Any], snapshot: CapitalLedgerSnapshot) -> datetime:
    for key in ("captured_at", "anchor_at", "projection_anchor_at"):
        raw = metadata.get(key)
        if raw is None:
            continue
        if isinstance(raw, datetime):
            value = raw
        else:
            try:
                value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                continue
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    updated_at = snapshot.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return updated_at.astimezone(timezone.utc)


class CapitalLedgerChange(BaseModel):
    schema_version: str = "v1"
    change_id: str = Field(default_factory=lambda: f"chg_{uuid4().hex[:12]}")
    run_id: str
    trade_id: str
    venue: VenueName
    cash_before: float
    cash_after: float
    reserved_cash_before: float
    reserved_cash_after: float
    realized_pnl_before: float
    realized_pnl_after: float
    unrealized_pnl_before: float
    unrealized_pnl_after: float
    equity_before: float
    equity_after: float
    positions_before: list[LedgerPosition] = Field(default_factory=list)
    positions_after: list[LedgerPosition] = Field(default_factory=list)
    fill_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapitalControlState(BaseModel):
    schema_version: str = "v1"
    state_id: str = Field(default_factory=lambda: f"ccs_{uuid4().hex[:12]}")
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    capital_available_usd: float = 0.0
    cash_available_usd: float = 0.0
    cash_locked_usd: float = 0.0
    raw_capital_available_usd: float = 0.0
    withdrawable_amount_usd: float = 0.0
    min_free_cash_buffer_pct: float = 0.0
    free_cash_buffer_usd: float = 0.0
    collateral_currency: str = "USD"
    per_venue_balance_cap_usd: float = 0.0
    venue_balance_usd: float = 0.0
    venue_balance_room_usd: float = 0.0
    max_market_exposure_usd: float = 0.0
    market_exposure_usd: float = 0.0
    market_exposure_room_usd: float = 0.0
    open_exposure_usd: float = 0.0
    max_open_positions: int = 0
    open_position_count: int = 0
    open_position_room: int = 0
    manual_review_count: int = 0
    max_daily_loss_usd: float = 0.0
    daily_loss_usd: float = 0.0
    equity_high_watermark: float = 0.0
    equity_drawdown_usd: float = 0.0
    equity_drawdown_pct: float = 0.0
    gross_position_exposure_usd: float = 0.0
    largest_position_notional_usd: float = 0.0
    largest_position_share: float = 0.0
    capital_fragmentation_score: float = 0.0
    capital_concentration_score: float = 0.0
    capital_by_venue_usd: dict[str, float] = Field(default_factory=dict)
    capital_by_market_usd: dict[str, float] = Field(default_factory=dict)
    transfer_latency_estimate_ms: float = 0.0
    max_capital_transfer_latency_ms: float = 0.0
    capital_transfer_latency_room_ms: float = 0.0
    capital_transfer_latency_exceeded: bool = False
    capital_frozen: bool = False
    reconciliation_open_drift: bool = False
    reconciliation_manual_review_required: bool = False
    reconciliation_drift_usd: float | None = None
    freeze_reasons: list[str] = Field(default_factory=list)
    warning_reasons: list[str] = Field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapitalLedgerStore:
    def __init__(self, paths: PredictionMarketPaths | None = None, *, base_dir: str | Path | None = None) -> None:
        if paths is not None:
            self.paths = paths
        elif base_dir is not None:
            self.paths = PredictionMarketPaths(Path(base_dir))
        else:
            self.paths = default_prediction_market_paths()
        self.paths.ensure_layout()
        self.root = self.paths.root / "capital_ledger"
        self.root.mkdir(parents=True, exist_ok=True)

    def save_snapshot(self, snapshot: CapitalLedgerSnapshot) -> Path:
        path = self.root / f"{snapshot.snapshot_id}.json"
        save_json(path, snapshot)
        return path

    def load_snapshot(self, snapshot_id: str) -> CapitalLedgerSnapshot:
        return CapitalLedgerSnapshot.model_validate_json((self.root / f"{snapshot_id}.json").read_text(encoding="utf-8"))

    def save_change(self, change: CapitalLedgerChange) -> Path:
        path = self.root / f"{change.change_id}.json"
        save_json(path, change)
        return path


@dataclass
class CapitalLedger:
    snapshot: CapitalLedgerSnapshot

    @classmethod
    def from_cash(
        cls,
        *,
        cash: float,
        venue: VenueName = VenueName.polymarket,
        reserved_cash: float = 0.0,
        currency: str = "USD",
        metadata: dict[str, Any] | None = None,
    ) -> "CapitalLedger":
        return cls(
            snapshot=CapitalLedgerSnapshot(
                venue=venue,
                cash=cash,
                reserved_cash=reserved_cash,
                currency=currency,
                metadata=metadata or {},
            )
        )

    @classmethod
    def from_snapshot(cls, snapshot: CapitalLedgerSnapshot) -> "CapitalLedger":
        return cls(snapshot=snapshot.model_copy(deep=True))

    def current_snapshot(self) -> CapitalLedgerSnapshot:
        self.snapshot.refresh_surface()
        return self.snapshot.model_copy(deep=True)

    def capital_by_venue(self) -> dict[VenueName, float]:
        capital: dict[VenueName, float] = {self.snapshot.venue: round(max(0.0, self.snapshot.cash + self.snapshot.reserved_cash), 6)}
        for position in self.snapshot.positions:
            notional = max(0.0, round(abs(position.quantity) * max(0.0, position.entry_price), 6))
            capital[position.venue] = round(capital.get(position.venue, 0.0) + notional, 6)
        return capital

    def capital_available_usd(
        self,
        *,
        extra_metadata: Mapping[str, Any] | None = None,
        reconciliation_open_drift: bool = False,
        reconciliation_manual_review_required: bool = False,
        reconciliation_drift_usd: float | None = None,
        venue: VenueName | None = None,
        market_id: str | None = None,
        min_free_cash_buffer_pct: float | None = None,
        per_venue_balance_cap_usd: float | None = None,
        max_market_exposure_usd: float | None = None,
        max_open_positions: int | None = None,
        max_daily_loss_usd: float | None = None,
        max_gross_position_exposure_usd: float | None = None,
        max_equity_drawdown_pct: float | None = None,
        max_position_concentration_share: float | None = None,
        max_capital_transfer_latency_ms: float | None = None,
    ) -> float:
        return self.capital_control_state(
            extra_metadata=extra_metadata,
            reconciliation_open_drift=reconciliation_open_drift,
            reconciliation_manual_review_required=reconciliation_manual_review_required,
            reconciliation_drift_usd=reconciliation_drift_usd,
            venue=venue,
            market_id=market_id,
            min_free_cash_buffer_pct=min_free_cash_buffer_pct,
            per_venue_balance_cap_usd=per_venue_balance_cap_usd,
            max_market_exposure_usd=max_market_exposure_usd,
            max_open_positions=max_open_positions,
            max_daily_loss_usd=max_daily_loss_usd,
            max_gross_position_exposure_usd=max_gross_position_exposure_usd,
            max_equity_drawdown_pct=max_equity_drawdown_pct,
            max_position_concentration_share=max_position_concentration_share,
            max_capital_transfer_latency_ms=max_capital_transfer_latency_ms,
        ).capital_available_usd

    def capital_control_state(
        self,
        *,
        extra_metadata: Mapping[str, Any] | None = None,
        reconciliation_open_drift: bool = False,
        reconciliation_manual_review_required: bool = False,
        reconciliation_drift_usd: float | None = None,
        venue: VenueName | None = None,
        market_id: str | None = None,
        min_free_cash_buffer_pct: float | None = None,
        per_venue_balance_cap_usd: float | None = None,
        max_market_exposure_usd: float | None = None,
        max_open_positions: int | None = None,
        max_daily_loss_usd: float | None = None,
        max_gross_position_exposure_usd: float | None = None,
        max_equity_drawdown_pct: float | None = None,
        max_position_concentration_share: float | None = None,
        max_capital_transfer_latency_ms: float | None = None,
    ) -> CapitalControlState:
        self.snapshot.refresh_surface()
        metadata = {**dict(self.snapshot.metadata or {}), **dict(extra_metadata or {})}
        captured_at = _resolve_captured_at(metadata, self.snapshot)
        freeze_reasons = capital_freeze_reasons(self.snapshot, extra_metadata=metadata)
        warning_reasons: list[str] = []
        raw_capital_available = round(max(0.0, self.snapshot.cash - self.snapshot.reserved_cash), 6)
        target_venue = venue or self.snapshot.venue
        target_market_id = str(market_id).strip() if market_id is not None and str(market_id).strip() else None
        equity = max(0.0, float(self.snapshot.equity or 0.0))
        equity_high_watermark = self.equity_high_watermark()
        equity_drawdown_usd = self.equity_drawdown_usd()
        equity_drawdown_pct = self.equity_drawdown_pct()
        gross_position_exposure_usd = self.gross_position_exposure_usd()
        open_exposure_usd = gross_position_exposure_usd
        largest_position_notional_usd = self.largest_position_notional_usd()
        largest_position_share = self.largest_position_share()
        capital_fragmentation_score = self.capital_fragmentation_score()
        capital_concentration_score = self.capital_concentration_score()
        capital_by_venue = {venue.value: amount for venue, amount in self.capital_by_venue().items()}
        capital_by_market = self.capital_by_market()
        free_cash_buffer_pct = _resolve_non_negative_float(
            min_free_cash_buffer_pct,
            metadata,
            "min_free_cash_buffer_pct",
        )
        per_venue_balance_cap = _resolve_non_negative_float(
            per_venue_balance_cap_usd,
            metadata,
            "per_venue_balance_cap_usd",
        )
        max_market_exposure = _resolve_non_negative_float(
            max_market_exposure_usd,
            metadata,
            "max_market_exposure_usd",
        )
        max_open_positions_value = _resolve_non_negative_int(
            max_open_positions,
            metadata,
            "max_open_positions",
        )
        max_daily_loss = _resolve_non_negative_float(
            max_daily_loss_usd,
            metadata,
            "max_daily_loss_usd",
        )
        max_transfer_latency = _resolve_non_negative_float(
            max_capital_transfer_latency_ms,
            metadata,
            "max_capital_transfer_latency_ms",
        )
        venue_balance_usd = self.venue_balance_usd(target_venue)
        market_exposure_usd = self.market_exposure_usd(target_market_id, venue=target_venue)
        open_position_count = self.open_position_count(venue=target_venue)
        manual_review_count = 0
        for key in ("manual_review_count", "manual_review_market_count"):
            raw_count = metadata.get(key)
            if raw_count is None:
                continue
            try:
                manual_review_count = max(0, int(raw_count))
                break
            except (TypeError, ValueError):
                continue
        if manual_review_count <= 0:
            for key in ("manual_review_market_ids", "manual_review_market_refs"):
                raw_value = metadata.get(key)
                if isinstance(raw_value, (list, tuple, set)):
                    manual_review_count = len([item for item in raw_value if str(item).strip()])
                    if manual_review_count > 0:
                        break
        daily_loss_usd = self.daily_loss_usd()
        drift_value = None
        if reconciliation_drift_usd is not None:
            try:
                drift_value = max(0.0, float(reconciliation_drift_usd))
            except (TypeError, ValueError):
                drift_value = None
        if drift_value is None:
            raw_drift = metadata.get("reconciliation_drift_usd") or metadata.get("open_reconciliation_drift_usd")
            if raw_drift is not None:
                try:
                    drift_value = max(0.0, float(raw_drift))
                except (TypeError, ValueError):
                    drift_value = None

        open_drift = bool(reconciliation_open_drift or metadata.get("reconciliation_open_drift"))
        manual_review = bool(reconciliation_manual_review_required or metadata.get("reconciliation_manual_review_required"))
        if drift_value is not None and drift_value > 0.0:
            open_drift = True
            warning_reasons.append(f"reconciliation_drift_usd:{drift_value:.6f}")
        if open_drift:
            freeze_reasons.append("reconciliation_open_drift")
        if manual_review:
            freeze_reasons.append("reconciliation_manual_review_required")
            manual_review_count = max(1, manual_review_count)
        if manual_review_count > 0:
            warning_reasons.append(f"manual_review_count:{manual_review_count}")

        free_cash_buffer_usd = round(equity * free_cash_buffer_pct, 6)
        capital_available = raw_capital_available
        if free_cash_buffer_pct > 0.0:
            capital_available = min(capital_available, max(0.0, raw_capital_available - free_cash_buffer_usd))
            if capital_available <= 0.0:
                freeze_reasons.append(
                    f"min_free_cash_buffer_pct_insufficient:{raw_capital_available:.6f}/{free_cash_buffer_usd:.6f}"
                )
            else:
                warning_reasons.append(f"min_free_cash_buffer_pct_applied:{free_cash_buffer_pct:.6f}")

        venue_balance_room_usd = 0.0
        if per_venue_balance_cap > 0.0:
            venue_balance_room_usd = max(0.0, per_venue_balance_cap - venue_balance_usd)
            capital_available = min(capital_available, venue_balance_room_usd)
            if venue_balance_room_usd <= 0.0:
                freeze_reasons.append(
                    f"per_venue_balance_cap_exceeded:{venue_balance_usd:.6f}/{per_venue_balance_cap:.6f}"
                )
            else:
                warning_reasons.append(f"per_venue_balance_cap_applied:{per_venue_balance_cap:.6f}")

        market_exposure_room_usd = 0.0
        if max_market_exposure > 0.0 and target_market_id is not None:
            market_exposure_room_usd = max(0.0, max_market_exposure - market_exposure_usd)
            capital_available = min(capital_available, market_exposure_room_usd)
            if market_exposure_room_usd <= 0.0:
                freeze_reasons.append(
                    f"max_market_exposure_usd_exceeded:{market_exposure_usd:.6f}/{max_market_exposure:.6f}"
                )
            else:
                warning_reasons.append(f"max_market_exposure_usd_applied:{max_market_exposure:.6f}")

        open_position_room = 0
        if max_open_positions_value > 0:
            open_position_room = max(0, max_open_positions_value - open_position_count)
            if open_position_room <= 0:
                freeze_reasons.append(f"max_open_positions_exceeded:{open_position_count}/{max_open_positions_value}")
                capital_available = 0.0
            elif open_position_room > 0:
                warning_reasons.append(f"max_open_positions_applied:{max_open_positions_value}")

        if max_daily_loss > 0.0 and daily_loss_usd >= max_daily_loss:
            freeze_reasons.append(f"max_daily_loss_usd_exceeded:{daily_loss_usd:.6f}/{max_daily_loss:.6f}")
            capital_available = 0.0
        elif max_daily_loss > 0.0 and daily_loss_usd > 0.0:
            warning_reasons.append(f"max_daily_loss_usd_applied:{max_daily_loss:.6f}")

        if max_gross_position_exposure_usd is not None and max_gross_position_exposure_usd > 0.0:
            if gross_position_exposure_usd > max_gross_position_exposure_usd:
                freeze_reasons.append(
                    f"gross_position_exposure_usd_exceeded:{gross_position_exposure_usd:.6f}/{max_gross_position_exposure_usd:.6f}"
                )
                capital_available = 0.0
            else:
                warning_reasons.append(f"gross_position_exposure_usd_applied:{max_gross_position_exposure_usd:.6f}")

        if max_equity_drawdown_pct is not None and max_equity_drawdown_pct > 0.0:
            if equity_drawdown_pct > max_equity_drawdown_pct:
                freeze_reasons.append(
                    f"equity_drawdown_pct_exceeded:{equity_drawdown_pct:.6f}/{max_equity_drawdown_pct:.6f}"
                )
                capital_available = 0.0
            else:
                warning_reasons.append(f"equity_drawdown_pct_applied:{max_equity_drawdown_pct:.6f}")

        if max_position_concentration_share is not None and max_position_concentration_share > 0.0:
            if largest_position_share > max_position_concentration_share:
                freeze_reasons.append(
                    f"position_concentration_share_exceeded:{largest_position_share:.6f}/{max_position_concentration_share:.6f}"
                )
                capital_available = 0.0
            else:
                warning_reasons.append(f"position_concentration_share_applied:{max_position_concentration_share:.6f}")

        capital_frozen = bool(freeze_reasons)
        if capital_frozen:
            capital_available = 0.0
        cash_available = round(max(0.0, capital_available), 6)
        cash_locked = round(max(0.0, self.snapshot.cash - cash_available), 6)
        withdrawable_amount = cash_available
        transfer_latency_estimate_ms = self.transfer_latency_estimate_ms()
        capital_transfer_latency_room_ms = 0.0
        capital_transfer_latency_exceeded = False
        if max_transfer_latency > 0.0:
            capital_transfer_latency_room_ms = round(max(0.0, max_transfer_latency - transfer_latency_estimate_ms), 6)
            capital_transfer_latency_exceeded = transfer_latency_estimate_ms > max_transfer_latency
            if capital_transfer_latency_exceeded:
                warning_reasons.append(
                    f"capital_transfer_latency_exceeded:{transfer_latency_estimate_ms:.6f}/{max_transfer_latency:.6f}"
                )
            else:
                warning_reasons.append(f"capital_transfer_latency_applied:{max_transfer_latency:.6f}")
        summary = (
            "capital_frozen"
            if capital_frozen
            else f"capital_available_usd={capital_available:.6f}"
        )
        summary = (
            f"{summary}; equity_drawdown_usd={equity_drawdown_usd:.6f}; equity_drawdown_pct={equity_drawdown_pct:.6f}; "
            f"gross_position_exposure_usd={gross_position_exposure_usd:.6f}; largest_position_share={largest_position_share:.6f}; "
            f"cash_locked_usd={cash_locked:.6f}; withdrawable_amount_usd={withdrawable_amount:.6f}; "
            f"capital_concentration_score={capital_concentration_score:.6f}"
        )
        if freeze_reasons:
            summary = f"{summary}; blocked={'|'.join(dict.fromkeys(freeze_reasons))}"
        elif warning_reasons:
            summary = f"{summary}; warnings={'|'.join(dict.fromkeys(warning_reasons))}"
        return CapitalControlState(
            captured_at=captured_at,
            capital_available_usd=capital_available,
            cash_available_usd=cash_available,
            cash_locked_usd=cash_locked,
            raw_capital_available_usd=raw_capital_available,
            withdrawable_amount_usd=withdrawable_amount,
            min_free_cash_buffer_pct=free_cash_buffer_pct,
            free_cash_buffer_usd=free_cash_buffer_usd,
            collateral_currency=self.snapshot.collateral_currency or self.snapshot.currency,
            per_venue_balance_cap_usd=per_venue_balance_cap,
            venue_balance_usd=venue_balance_usd,
            venue_balance_room_usd=venue_balance_room_usd,
            max_market_exposure_usd=max_market_exposure,
            market_exposure_usd=market_exposure_usd,
            market_exposure_room_usd=market_exposure_room_usd,
            open_exposure_usd=open_exposure_usd,
            max_open_positions=max_open_positions_value,
            open_position_count=open_position_count,
            open_position_room=open_position_room,
            manual_review_count=manual_review_count,
            max_daily_loss_usd=max_daily_loss,
            daily_loss_usd=daily_loss_usd,
            equity_high_watermark=equity_high_watermark,
            equity_drawdown_usd=equity_drawdown_usd,
            equity_drawdown_pct=equity_drawdown_pct,
            gross_position_exposure_usd=gross_position_exposure_usd,
            largest_position_notional_usd=largest_position_notional_usd,
            largest_position_share=largest_position_share,
            capital_fragmentation_score=capital_fragmentation_score,
            capital_concentration_score=capital_concentration_score,
            capital_by_venue_usd=capital_by_venue,
            capital_by_market_usd=capital_by_market,
            transfer_latency_estimate_ms=transfer_latency_estimate_ms,
            max_capital_transfer_latency_ms=max_transfer_latency,
            capital_transfer_latency_room_ms=capital_transfer_latency_room_ms,
            capital_transfer_latency_exceeded=capital_transfer_latency_exceeded,
            capital_frozen=capital_frozen,
            reconciliation_open_drift=open_drift,
            reconciliation_manual_review_required=manual_review,
            reconciliation_drift_usd=drift_value,
            freeze_reasons=list(dict.fromkeys(freeze_reasons)),
            warning_reasons=list(dict.fromkeys(warning_reasons)),
            summary=summary,
            metadata={
                "capital_available_usd": capital_available,
                "capital_available": capital_available,
                "cash_available_usd": cash_available,
                "cash_available": cash_available,
                "cash_locked_usd": cash_locked,
                "cash_locked": cash_locked,
                "raw_capital_available_usd": raw_capital_available,
                "withdrawable_amount_usd": withdrawable_amount,
                "withdrawable_amount": withdrawable_amount,
                "min_free_cash_buffer_pct": free_cash_buffer_pct,
                "free_cash_buffer_usd": free_cash_buffer_usd,
                "collateral_currency": self.snapshot.collateral_currency or self.snapshot.currency,
                "per_venue_balance_cap_usd": per_venue_balance_cap,
                "venue_balance_usd": venue_balance_usd,
                "venue_balance_room_usd": venue_balance_room_usd,
                "max_market_exposure_usd": max_market_exposure,
                "market_exposure_usd": market_exposure_usd,
                "market_exposure_room_usd": market_exposure_room_usd,
                "open_exposure_usd": open_exposure_usd,
                "max_open_positions": max_open_positions_value,
                "open_position_count": open_position_count,
                "open_position_room": open_position_room,
                "manual_review_count": manual_review_count,
                "max_daily_loss_usd": max_daily_loss,
                "daily_loss_usd": daily_loss_usd,
                "equity_high_watermark": equity_high_watermark,
                "equity_drawdown_usd": equity_drawdown_usd,
                "equity_drawdown_pct": equity_drawdown_pct,
                "gross_position_exposure_usd": gross_position_exposure_usd,
                "largest_position_notional_usd": largest_position_notional_usd,
                "largest_position_share": largest_position_share,
                "capital_fragmentation_score": capital_fragmentation_score,
                "capital_concentration_score": capital_concentration_score,
                "capital_by_venue_usd": capital_by_venue,
                "capital_by_venue": capital_by_venue,
                "capital_by_market_usd": capital_by_market,
                "capital_by_market": capital_by_market,
                "transfer_latency_estimate_ms": transfer_latency_estimate_ms,
                "max_capital_transfer_latency_ms": max_transfer_latency,
                "capital_transfer_latency_room_ms": capital_transfer_latency_room_ms,
                "capital_transfer_latency_exceeded": capital_transfer_latency_exceeded,
                "captured_at": captured_at.isoformat(),
                "target_venue": target_venue.value,
                "target_market_id": target_market_id,
                "capital_frozen": capital_frozen,
                "reconciliation_open_drift": open_drift,
                "reconciliation_manual_review_required": manual_review,
                "reconciliation_drift_usd": drift_value,
                "freeze_reasons": list(dict.fromkeys(freeze_reasons)),
                "warning_reasons": list(dict.fromkeys(warning_reasons)),
                "summary": summary,
            },
        )

    def venue_balance_usd(self, venue: VenueName | None = None) -> float:
        target = venue or self.snapshot.venue
        capital = self.capital_by_venue()
        return round(max(0.0, float(capital.get(target, 0.0))), 6)

    def capital_by_market(self) -> dict[str, float]:
        capital: dict[str, float] = {}
        for position in self.snapshot.positions:
            notional = max(0.0, round(abs(position.quantity) * max(0.0, position.entry_price), 6))
            capital[position.market_id] = round(capital.get(position.market_id, 0.0) + notional, 6)
        return capital

    def market_exposure_usd(self, market_id: str | None, *, venue: VenueName | None = None) -> float:
        if market_id is None:
            return 0.0
        target_venue = venue
        exposure = 0.0
        for position in self.snapshot.positions:
            if position.market_id != market_id:
                continue
            if target_venue is not None and position.venue != target_venue:
                continue
            price = position.mark_price if position.mark_price is not None else position.entry_price
            exposure += abs(float(position.quantity)) * max(0.0, float(price))
        return round(max(0.0, exposure), 6)

    def open_position_count(self, *, venue: VenueName | None = None) -> int:
        open_markets: set[tuple[VenueName, str]] = set()
        for position in self.snapshot.positions:
            if abs(float(position.quantity)) <= 1e-12:
                continue
            if venue is not None and position.venue != venue:
                continue
            open_markets.add((position.venue, position.market_id))
        return len(open_markets)

    def market_is_open(self, market_id: str, *, venue: VenueName | None = None) -> bool:
        for position in self.snapshot.positions:
            if position.market_id != market_id:
                continue
            if venue is not None and position.venue != venue:
                continue
            if abs(float(position.quantity)) > 1e-12:
                return True
        return False

    def daily_loss_usd(self) -> float:
        metadata = self.snapshot.metadata or {}
        for key in ("daily_loss_usd", "intraday_loss_usd"):
            value = _metadata_float(metadata, key)
            if value is not None:
                return round(max(0.0, value), 6)
        for key in ("daily_realized_pnl_usd", "intraday_realized_pnl_usd", "session_realized_pnl_usd"):
            value = _metadata_float(metadata, key)
            if value is not None:
                return round(max(0.0, -value), 6)
        for key in ("day_start_equity", "session_start_equity", "equity_at_day_start"):
            value = _metadata_float(metadata, key)
            if value is not None:
                return round(max(0.0, value - float(self.snapshot.equity or 0.0)), 6)
        return 0.0

    def capital_fragmentation_score(self) -> float:
        capital = self.capital_by_venue()
        total = sum(capital.values())
        if total <= 1e-12:
            return 0.0
        shares = [value / total for value in capital.values() if value > 0.0]
        hhi = sum(share * share for share in shares)
        return round(max(0.0, min(1.0, 1.0 - hhi)), 6)

    def capital_concentration_score(self) -> float:
        capital = self.capital_by_venue()
        total = sum(capital.values())
        if total <= 1e-12:
            return 0.0
        shares = [value / total for value in capital.values() if value > 0.0]
        hhi = sum(share * share for share in shares)
        return round(max(0.0, min(1.0, hhi)), 6)

    def gross_position_exposure_usd(self) -> float:
        return round(sum(_position_notional(position) for position in self.snapshot.positions), 6)

    def largest_position_notional_usd(self) -> float:
        if not self.snapshot.positions:
            return 0.0
        return round(max(_position_notional(position) for position in self.snapshot.positions), 6)

    def largest_position_share(self) -> float:
        gross_exposure = self.gross_position_exposure_usd()
        if gross_exposure <= 1e-12:
            return 0.0
        return round(max(0.0, self.largest_position_notional_usd() / gross_exposure), 6)

    def equity_high_watermark(self) -> float:
        value = _metadata_float(self.snapshot.metadata or {}, "equity_high_watermark")
        if value is not None:
            return round(max(0.0, value), 6)
        return round(max(0.0, float(self.snapshot.equity or 0.0)), 6)

    def equity_drawdown_usd(self) -> float:
        high_watermark = self.equity_high_watermark()
        return round(max(0.0, high_watermark - float(self.snapshot.equity or 0.0)), 6)

    def equity_drawdown_pct(self) -> float:
        high_watermark = self.equity_high_watermark()
        if high_watermark <= 1e-12:
            return 0.0
        return round(max(0.0, self.equity_drawdown_usd() / high_watermark), 6)

    def transfer_latency_estimate_ms(self) -> float:
        capital = self.capital_by_venue()
        venue_count = sum(1 for value in capital.values() if value > 0.0)
        if venue_count <= 1:
            return 0.0
        position_count = len(self.snapshot.positions)
        base_ms = 15_000.0
        venue_component = 3_500.0 * max(0, venue_count - 1)
        position_component = 750.0 * max(0, position_count - 1)
        return round(base_ms + venue_component + position_component, 2)

    def reallocation_cost_estimate_usd(
        self,
        *,
        reallocation_fee_bps: float | None = None,
        opportunity_cost_bps_per_day: float | None = None,
    ) -> float:
        capital = self.capital_by_venue()
        total_capital = sum(capital.values())
        if total_capital <= 1e-12:
            return 0.0
        if len([value for value in capital.values() if value > 0.0]) <= 1:
            return 0.0

        fee_bps = float(self.snapshot.metadata.get("reallocation_fee_bps", 12.5) if reallocation_fee_bps is None else reallocation_fee_bps)
        opp_bps_per_day = float(
            self.snapshot.metadata.get("opportunity_cost_bps_per_day", 2.0)
            if opportunity_cost_bps_per_day is None
            else opportunity_cost_bps_per_day
        )
        latency_ms = self.transfer_latency_estimate_ms()
        fee_cost = total_capital * max(0.0, fee_bps) / 10_000.0
        opportunity_cost = total_capital * max(0.0, opp_bps_per_day) / 10_000.0 * (latency_ms / 86_400_000.0)
        return round(fee_cost + opportunity_cost, 6)

    def reserve_cash(self, amount: float, *, note: str | None = None) -> None:
        amount = max(0.0, float(amount))
        self.snapshot.cash = round(max(0.0, self.snapshot.cash - amount), 6)
        self.snapshot.reserved_cash = round(self.snapshot.reserved_cash + amount, 6)
        self.snapshot.metadata.setdefault("reserve_notes", [])
        if note:
            self.snapshot.metadata["reserve_notes"].append(note)
        self._refresh_equity()

    def release_cash(self, amount: float, *, note: str | None = None) -> None:
        amount = max(0.0, float(amount))
        self.snapshot.cash = round(self.snapshot.cash + amount, 6)
        self.snapshot.reserved_cash = round(max(0.0, self.snapshot.reserved_cash - amount), 6)
        self.snapshot.metadata.setdefault("release_notes", [])
        if note:
            self.snapshot.metadata["release_notes"].append(note)
        self._refresh_equity()

    def apply_paper_trade(
        self,
        paper_trade: PaperTradeSimulation,
        *,
        mark_price: float | None = None,
    ) -> CapitalLedgerChange:
        cash_before = self.snapshot.cash
        reserved_before = self.snapshot.reserved_cash
        realized_before = self.snapshot.realized_pnl
        unrealized_before = self.snapshot.unrealized_pnl
        equity_before = self.snapshot.equity
        positions_before = [position.model_copy(deep=True) for position in self.snapshot.positions]

        realized_delta = 0.0
        for fill in paper_trade.fills:
            realized_delta += self._apply_fill(
                market_id=paper_trade.market_id,
                venue=paper_trade.venue,
                position_side=fill.position_side,
                execution_side=fill.execution_side,
                quantity=fill.filled_quantity,
                price=fill.fill_price,
                fee_paid=fill.fee_paid,
            )

        self.snapshot.realized_pnl = round(self.snapshot.realized_pnl + realized_delta, 6)
        self._mark_to_market(mark_price if mark_price is not None else paper_trade.reference_price)
        self._refresh_equity()

        change = CapitalLedgerChange(
            run_id=paper_trade.run_id,
            trade_id=paper_trade.trade_id,
            venue=paper_trade.venue,
            cash_before=cash_before,
            cash_after=self.snapshot.cash,
            reserved_cash_before=reserved_before,
            reserved_cash_after=self.snapshot.reserved_cash,
            realized_pnl_before=realized_before,
            realized_pnl_after=self.snapshot.realized_pnl,
            unrealized_pnl_before=unrealized_before,
            unrealized_pnl_after=self.snapshot.unrealized_pnl,
            equity_before=equity_before,
            equity_after=self.snapshot.equity,
            positions_before=positions_before,
            positions_after=[position.model_copy(deep=True) for position in self.snapshot.positions],
            fill_count=len(paper_trade.fills),
            metadata={
                "paper_trade_status": paper_trade.status.value,
                "paper_trade_direction": paper_trade.execution_side.value,
                "position_side": paper_trade.position_side.value,
            },
        )
        self.snapshot.metadata.setdefault("changes", []).append(change.change_id)
        return change

    def mark_to_market(self, *, mark_price: float | None, market_id: str | None = None) -> CapitalLedgerSnapshot:
        self._mark_to_market(mark_price, market_id=market_id)
        self._refresh_equity()
        return self.current_snapshot()

    def position(self, market_id: str, side: TradeSide, venue: VenueName | None = None) -> LedgerPosition | None:
        for position in self.snapshot.positions:
            if position.market_id == market_id and position.side == side and (venue is None or position.venue == venue):
                return position
        return None

    def persist(self, store: CapitalLedgerStore | None = None) -> Path:
        store = store or CapitalLedgerStore()
        return store.save_snapshot(self.snapshot)

    def _apply_fill(
        self,
        *,
        market_id: str,
        venue: VenueName,
        position_side: TradeSide,
        execution_side: TradeSide,
        quantity: float,
        price: float,
        fee_paid: float,
    ) -> float:
        if quantity <= 0:
            return 0.0
        signed_delta = quantity if execution_side == TradeSide.buy else -quantity
        cash_flow = -quantity * price if execution_side == TradeSide.buy else quantity * price
        cash_flow -= fee_paid
        self.snapshot.cash = round(self.snapshot.cash + cash_flow, 6)

        position = self._find_position(market_id, venue, position_side)
        if position is None:
            position = LedgerPosition(
                market_id=market_id,
                venue=venue,
                side=position_side,
                quantity=0.0,
                entry_price=price,
            )
            self.snapshot.positions.append(position)

        realized_delta, new_qty, new_entry = _update_position(position.quantity, position.entry_price, signed_delta, price)
        position.quantity = round(new_qty, 8)
        position.entry_price = round(new_entry, 6)
        position.mark_price = position.mark_price if position.mark_price is not None else price
        position.unrealized_pnl = _unrealized(position.quantity, position.entry_price, position.mark_price, position.side)

        if abs(position.quantity) <= 1e-12:
            self.snapshot.positions = [
                item
                for item in self.snapshot.positions
                if not (item.market_id == market_id and item.venue == venue and item.side == position_side)
            ]
        return realized_delta

    def _mark_to_market(self, mark_price: float | None, *, market_id: str | None = None) -> None:
        if mark_price is None:
            for position in self.snapshot.positions:
                position.unrealized_pnl = 0.0
            self.snapshot.unrealized_pnl = 0.0
            return

        total = 0.0
        for position in self.snapshot.positions:
            if market_id is not None and position.market_id != market_id:
                continue
            side_mark = _side_mark_price(mark_price, position.side)
            position.mark_price = round(side_mark, 6)
            position.unrealized_pnl = _unrealized(position.quantity, position.entry_price, side_mark, position.side)
            total += position.unrealized_pnl or 0.0
        self.snapshot.unrealized_pnl = round(total, 6)

    def _refresh_equity(self) -> None:
        self.snapshot.equity = round(
            self.snapshot.cash - self.snapshot.reserved_cash + self.snapshot.realized_pnl + self.snapshot.unrealized_pnl,
            6,
        )
        peak_equity = self.snapshot.metadata.get("equity_high_watermark")
        try:
            peak_equity_value = max(0.0, float(peak_equity)) if peak_equity is not None else self.snapshot.equity
        except (TypeError, ValueError):
            peak_equity_value = self.snapshot.equity
        self.snapshot.metadata["equity_high_watermark"] = round(max(peak_equity_value, self.snapshot.equity), 6)
        self.snapshot.metadata["equity_drawdown"] = round(
            max(0.0, self.snapshot.metadata["equity_high_watermark"] - self.snapshot.equity),
            6,
        )
        capital_by_venue = {venue.value: amount for venue, amount in self.capital_by_venue().items()}
        capital_by_market = self.capital_by_market()
        self.snapshot.metadata["capital_by_venue"] = capital_by_venue
        self.snapshot.metadata["capital_by_market_usd"] = capital_by_market
        self.snapshot.metadata["capital_fragmentation_score"] = self.capital_fragmentation_score()
        self.snapshot.metadata["capital_concentration_score"] = self.capital_concentration_score()
        self.snapshot.metadata["gross_position_exposure_usd"] = self.gross_position_exposure_usd()
        self.snapshot.metadata["largest_position_notional_usd"] = self.largest_position_notional_usd()
        self.snapshot.metadata["largest_position_share"] = self.largest_position_share()
        self.snapshot.metadata["equity_high_watermark"] = self.equity_high_watermark()
        self.snapshot.metadata["equity_drawdown_usd"] = self.equity_drawdown_usd()
        self.snapshot.metadata["equity_drawdown_pct"] = self.equity_drawdown_pct()
        self.snapshot.metadata["transfer_latency_estimate_ms"] = self.transfer_latency_estimate_ms()
        self.snapshot.metadata["reallocation_cost_estimate_usd"] = self.reallocation_cost_estimate_usd()
        self.snapshot.updated_at = datetime.now(timezone.utc)
        self.snapshot.refresh_surface()

    def _find_position(self, market_id: str, venue: VenueName, side: TradeSide) -> LedgerPosition | None:
        for position in self.snapshot.positions:
            if position.market_id == market_id and position.venue == venue and position.side == side:
                return position
        return None


def capital_freeze_reasons(
    snapshot: CapitalLedgerSnapshot,
    *,
    extra_metadata: Mapping[str, Any] | None = None,
) -> list[str]:
    metadata = {**dict(snapshot.metadata or {}), **dict(extra_metadata or {})}
    reasons: list[str] = []
    frozen = bool(
        metadata.get("capital_frozen")
        or metadata.get("capital_freeze")
        or metadata.get("capital_freeze_active")
        or metadata.get("freeze_capital")
    )
    if frozen:
        reasons.append("capital_frozen")
    freeze_reason = metadata.get("capital_freeze_reason") or metadata.get("capital_freeze_note")
    if freeze_reason:
        reasons.append(f"capital_freeze_reason:{freeze_reason}")
    freeze_until = metadata.get("capital_frozen_until") or metadata.get("capital_freeze_until")
    if freeze_until:
        reasons.append(f"capital_freeze_until:{freeze_until}")
    freeze_source = metadata.get("capital_freeze_source")
    if freeze_source:
        reasons.append(f"capital_freeze_source:{freeze_source}")
    if metadata.get("reconciliation_open_drift"):
        reasons.append("reconciliation_open_drift")
    if metadata.get("new_orders_blocked"):
        reasons.append("new_orders_blocked")
    if metadata.get("reconciliation_new_orders_blocked"):
        reasons.append("reconciliation_new_orders_blocked")
    if metadata.get("reconciliation_manual_review_required"):
        reasons.append("reconciliation_manual_review_required")
    reconciliation_drift = metadata.get("reconciliation_drift_usd")
    if reconciliation_drift is not None:
        try:
            drift_value = max(0.0, float(reconciliation_drift))
        except (TypeError, ValueError):
            drift_value = 0.0
        if drift_value > 0.0:
            reasons.append(f"reconciliation_drift_usd:{drift_value:.6f}")
    return list(dict.fromkeys(reasons))


def capital_is_frozen(
    snapshot: CapitalLedgerSnapshot,
    *,
    extra_metadata: Mapping[str, Any] | None = None,
) -> bool:
    return bool(capital_freeze_reasons(snapshot, extra_metadata=extra_metadata))


def _resolve_non_negative_float(value: float | None, metadata: Mapping[str, Any], key: str) -> float:
    if value is not None:
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0
    metadata_value = _metadata_float(metadata, key)
    return 0.0 if metadata_value is None else max(0.0, metadata_value)


def _resolve_non_negative_int(value: int | None, metadata: Mapping[str, Any], key: str) -> int:
    if value is not None:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0
    metadata_value = metadata.get(key)
    if metadata_value is None:
        return 0
    try:
        return max(0, int(metadata_value))
    except (TypeError, ValueError):
        return 0


def _metadata_float(metadata: Mapping[str, Any], key: str) -> float | None:
    value = metadata.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _update_position(
    current_quantity: float,
    current_entry_price: float,
    delta_quantity: float,
    fill_price: float,
) -> tuple[float, float, float]:
    if abs(delta_quantity) <= 1e-12:
        return 0.0, current_quantity, current_entry_price
    if abs(current_quantity) <= 1e-12:
        return 0.0, delta_quantity, fill_price
    if current_quantity * delta_quantity > 0:
        new_quantity = current_quantity + delta_quantity
        weighted_entry = (
            abs(current_quantity) * current_entry_price + abs(delta_quantity) * fill_price
        ) / max(1e-12, abs(current_quantity) + abs(delta_quantity))
        return 0.0, new_quantity, weighted_entry

    closed_quantity = min(abs(current_quantity), abs(delta_quantity))
    if current_quantity > 0 and delta_quantity < 0:
        realized = (fill_price - current_entry_price) * closed_quantity
    elif current_quantity < 0 and delta_quantity > 0:
        realized = (current_entry_price - fill_price) * closed_quantity
    else:
        realized = 0.0

    remaining = abs(delta_quantity) - abs(current_quantity)
    if remaining > 1e-12:
        new_quantity = remaining if delta_quantity > 0 else -remaining
        return realized, new_quantity, fill_price
    if abs(remaining) <= 1e-12:
        return realized, 0.0, fill_price
    new_quantity = current_quantity + delta_quantity
    if abs(new_quantity) <= 1e-12:
        return realized, 0.0, fill_price
    return realized, new_quantity, current_entry_price


def _unrealized(quantity: float, entry_price: float, mark_price: float, side: TradeSide) -> float:
    if abs(quantity) <= 1e-12:
        return 0.0
    if quantity > 0:
        return round((mark_price - entry_price) * quantity, 6)
    return round((entry_price - mark_price) * abs(quantity), 6)


def _side_mark_price(mark_price: float, side: TradeSide) -> float:
    if side == TradeSide.no:
        return round(max(0.0, min(1.0, 1.0 - float(mark_price))), 6)
    return round(max(0.0, min(1.0, float(mark_price))), 6)


def _position_notional(position: LedgerPosition) -> float:
    price = position.mark_price if position.mark_price is not None else position.entry_price
    return round(abs(float(position.quantity)) * max(0.0, float(price)), 6)
