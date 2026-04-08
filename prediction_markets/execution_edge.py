from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from .models import (
    CrossVenueMatch,
    MarketDescriptor,
    TradeSide,
    VenueName,
    VenueType,
    _first_non_empty,
    _metadata_string,
    _normalized_text,
    _stable_content_hash,
    _utc_datetime,
    _utc_now,
)


_MIN_EXECUTABLE_EDGE_BPS = 20.0
_MIN_EXECUTABLE_CONFIDENCE = 0.65


def _edge_friction_budget_bps(*, fees_bps: float, slippage_bps: float, hedge_risk_bps: float) -> float:
    return round(max(0.0, float(fees_bps) + float(slippage_bps) + float(hedge_risk_bps)), 6)


class MarketEquivalenceProofStatus(str, Enum):
    proven = "proven"
    partial = "partial"
    rejected = "rejected"
    needs_review = "needs_review"


class MarketEquivalenceProof(BaseModel):
    schema_version: str = "v1"
    proof_id: str = Field(default_factory=lambda: f"meq_{uuid4().hex[:12]}")
    market_a_ref: str
    market_b_ref: str
    canonical_event_id: str
    proof_status: MarketEquivalenceProofStatus = MarketEquivalenceProofStatus.needs_review
    resolution_compatibility: float = 0.0
    payout_compatibility: float = 0.0
    currency_compatibility: float = 0.0
    timing_compatibility: float = 0.0
    mismatch_reasons: list[str] = Field(default_factory=list)
    manual_review_required: bool = True
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @field_validator(
        "resolution_compatibility",
        "payout_compatibility",
        "currency_compatibility",
        "timing_compatibility",
    )
    @classmethod
    def _clamp_score(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @model_validator(mode="after")
    def _normalize(self) -> "MarketEquivalenceProof":
        self.market_a_ref = _normalized_text(self.market_a_ref)
        self.market_b_ref = _normalized_text(self.market_b_ref)
        self.canonical_event_id = _normalized_text(self.canonical_event_id)
        self.mismatch_reasons = list(dict.fromkeys(_normalized_text(reason) for reason in self.mismatch_reasons if _normalized_text(reason)))
        if self.proof_status == MarketEquivalenceProofStatus.needs_review:
            self.proof_status = _derive_proof_status(self)
        self.manual_review_required = self.manual_review_required or self.proof_status != MarketEquivalenceProofStatus.proven
        if not self.rationale:
            self.rationale = _proof_rationale(self)
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        return self

    def surface(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "MarketEquivalenceProof":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class ExecutableEdge(BaseModel):
    schema_version: str = "v1"
    edge_id: str = Field(default_factory=lambda: f"xedge_{uuid4().hex[:12]}")
    market_ref: str
    counterparty_market_ref: str | None = None
    proof_ref: str | None = None
    raw_edge_bps: float = 0.0
    fees_bps: float = 0.0
    slippage_bps: float = 0.0
    hedge_risk_bps: float = 0.0
    executable_edge_bps: float | None = None
    confidence: float = 0.0
    expires_at: datetime = Field(default_factory=lambda: _utc_now() + timedelta(hours=6))
    manual_review_required: bool = False
    reason_codes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @field_validator("raw_edge_bps", "fees_bps", "slippage_bps", "hedge_risk_bps", "confidence", mode="before")
    @classmethod
    def _coerce_float(cls, value: Any) -> float:
        if value is None:
            return 0.0
        return float(value)

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @model_validator(mode="after")
    def _normalize(self) -> "ExecutableEdge":
        self.market_ref = _normalized_text(self.market_ref)
        self.counterparty_market_ref = _first_non_empty(self.counterparty_market_ref)
        self.proof_ref = _first_non_empty(self.proof_ref)
        self.expires_at = _utc_datetime(self.expires_at) or (_utc_now() + timedelta(hours=6))
        friction_budget_bps = _edge_friction_budget_bps(
            fees_bps=self.fees_bps,
            slippage_bps=self.slippage_bps,
            hedge_risk_bps=self.hedge_risk_bps,
        )
        if self.executable_edge_bps is None:
            self.executable_edge_bps = round(
                max(0.0, float(self.raw_edge_bps) - friction_budget_bps),
                6,
            )
        else:
            self.executable_edge_bps = round(max(0.0, float(self.executable_edge_bps)), 6)
        self.reason_codes = list(dict.fromkeys(_normalized_text(reason) for reason in self.reason_codes if _normalized_text(reason)))
        self.metadata = {
            **dict(self.metadata),
            "gross_edge_bps": round(float(self.raw_edge_bps), 6),
            "friction_budget_bps": friction_budget_bps,
            "net_edge_margin_bps": round(float(self.executable_edge_bps) - _MIN_EXECUTABLE_EDGE_BPS, 6),
            "confidence_gate": _MIN_EXECUTABLE_CONFIDENCE,
            "executable_threshold_bps": _MIN_EXECUTABLE_EDGE_BPS,
        }
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        return self

    @property
    def executable(self) -> bool:
        return (
            self.executable_edge_bps >= _MIN_EXECUTABLE_EDGE_BPS
            and self.confidence >= _MIN_EXECUTABLE_CONFIDENCE
            and not self.manual_review_required
        )

    def surface(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "ExecutableEdge":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class ArbPlanLeg(BaseModel):
    schema_version: str = "v1"
    leg_id: str = Field(default_factory=lambda: f"arbleg_{uuid4().hex[:12]}")
    market_ref: str
    venue: VenueName
    side: TradeSide
    notional_usd: float = 0.0
    position_side: TradeSide | None = None
    limit_price: float | None = None
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @field_validator("notional_usd", "limit_price", mode="before")
    @classmethod
    def _coerce_float(cls, value: Any) -> float | None:
        if value is None:
            return None
        return float(value)

    @model_validator(mode="after")
    def _normalize(self) -> "ArbPlanLeg":
        self.market_ref = _normalized_text(self.market_ref)
        if self.position_side is not None and not isinstance(self.position_side, TradeSide):
            self.position_side = TradeSide(str(self.position_side))
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        return self


class ArbPlan(BaseModel):
    schema_version: str = "v1"
    arb_plan_id: str = Field(default_factory=lambda: f"arbplan_{uuid4().hex[:12]}")
    proof_ref: str
    edge_ref: str
    market_a_ref: str
    market_b_ref: str
    canonical_event_id: str
    legs: list[ArbPlanLeg] = Field(default_factory=list)
    required_capital_usd: float = 0.0
    break_even_after_fees_bps: float = 0.0
    max_unhedged_leg_ms: int = 0
    hedge_completion_ratio: float = 0.0
    hedge_completion_ready: bool = False
    legging_risk_reasons: list[str] = Field(default_factory=list)
    exit_policy: str = "close_on_edge_decay"
    manual_review_required: bool = True
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @field_validator("required_capital_usd", "break_even_after_fees_bps", mode="before")
    @classmethod
    def _coerce_float(cls, value: Any) -> float:
        if value is None:
            return 0.0
        return max(0.0, float(value))

    @field_validator("max_unhedged_leg_ms", mode="before")
    @classmethod
    def _coerce_int(cls, value: Any) -> int:
        if value is None:
            return 0
        return max(0, int(value))

    @field_validator("hedge_completion_ratio", mode="before")
    @classmethod
    def _coerce_ratio(cls, value: Any) -> float:
        if value is None:
            return 0.0
        return max(0.0, min(1.0, float(value)))

    @model_validator(mode="after")
    def _normalize(self) -> "ArbPlan":
        self.proof_ref = _normalized_text(self.proof_ref)
        self.edge_ref = _normalized_text(self.edge_ref)
        self.market_a_ref = _normalized_text(self.market_a_ref)
        self.market_b_ref = _normalized_text(self.market_b_ref)
        self.canonical_event_id = _normalized_text(self.canonical_event_id)
        self.exit_policy = _normalized_text(self.exit_policy) or "close_on_edge_decay"
        self.legging_risk_reasons = list(
            dict.fromkeys(_normalized_text(reason) for reason in self.legging_risk_reasons if _normalized_text(reason))
        )
        if not self.rationale:
            self.rationale = _plan_rationale(self)
        self.legs = [leg.model_copy() for leg in self.legs]
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        return self

    @property
    def executable(self) -> bool:
        return not self.manual_review_required and len(self.legs) >= 2 and self.break_even_after_fees_bps >= 0.0

    @property
    def legging_risk(self) -> bool:
        return bool(self.legging_risk_reasons) or self.max_unhedged_leg_ms > 0 or not self.hedge_completion_ready

    def surface(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "ArbPlan":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


def assess_market_equivalence(
    market_a: MarketDescriptor,
    market_b: MarketDescriptor,
    *,
    match: CrossVenueMatch | None = None,
) -> MarketEquivalenceProof:
    canonical_event_id = _first_non_empty(
        match.canonical_event_id if match is not None else None,
        market_a.canonical_event_id,
        market_b.canonical_event_id,
        market_a.event_id,
        market_b.event_id,
        market_a.market_id,
        market_b.market_id,
    ) or f"{market_a.market_id}__{market_b.market_id}"
    resolution_compatibility, resolution_reasons = _resolution_compatibility(market_a, market_b, match=match)
    payout_compatibility, payout_reasons = _payout_compatibility(market_a, market_b, match=match)
    currency_compatibility, currency_reasons = _currency_compatibility(market_a, market_b, match=match)
    timing_compatibility, timing_reasons = _timing_compatibility(market_a, market_b)
    mismatch_reasons = resolution_reasons + payout_reasons + currency_reasons + timing_reasons
    proof_status = _derive_status_from_scores(
        resolution_compatibility=resolution_compatibility,
        payout_compatibility=payout_compatibility,
        currency_compatibility=currency_compatibility,
        timing_compatibility=timing_compatibility,
        mismatch_reasons=mismatch_reasons,
    )
    return MarketEquivalenceProof(
        market_a_ref=market_a.market_id,
        market_b_ref=market_b.market_id,
        canonical_event_id=canonical_event_id,
        proof_status=proof_status,
        resolution_compatibility=resolution_compatibility,
        payout_compatibility=payout_compatibility,
        currency_compatibility=currency_compatibility,
        timing_compatibility=timing_compatibility,
        mismatch_reasons=mismatch_reasons,
        manual_review_required=proof_status != MarketEquivalenceProofStatus.proven,
        metadata={
            "market_a_title": market_a.title,
            "market_b_title": market_b.title,
            "market_a_venue": market_a.venue.value,
            "market_b_venue": market_b.venue.value,
        },
    )


def _derive_status_from_scores(
    *,
    resolution_compatibility: float,
    payout_compatibility: float,
    currency_compatibility: float,
    timing_compatibility: float,
    mismatch_reasons: list[str],
) -> MarketEquivalenceProofStatus:
    scores = [
        max(0.0, min(1.0, float(resolution_compatibility))),
        max(0.0, min(1.0, float(payout_compatibility))),
        max(0.0, min(1.0, float(currency_compatibility))),
        max(0.0, min(1.0, float(timing_compatibility))),
    ]
    if any(score == 0.0 for score in scores) and mismatch_reasons:
        return MarketEquivalenceProofStatus.rejected
    if all(score >= 0.95 for score in scores) and not mismatch_reasons:
        return MarketEquivalenceProofStatus.proven
    if any(reason.endswith("_missing") for reason in mismatch_reasons):
        return MarketEquivalenceProofStatus.needs_review
    return MarketEquivalenceProofStatus.partial


def derive_executable_edge(
    proof: MarketEquivalenceProof,
    *,
    market_ref: str,
    counterparty_market_ref: str | None = None,
    raw_edge_bps: float,
    fees_bps: float = 0.0,
    slippage_bps: float = 0.0,
    hedge_risk_bps: float = 0.0,
    confidence: float = 0.0,
    expires_at: datetime | None = None,
) -> ExecutableEdge:
    reason_codes: list[str] = []
    manual_review_required = proof.manual_review_required
    friction_budget_bps = _edge_friction_budget_bps(
        fees_bps=fees_bps,
        slippage_bps=slippage_bps,
        hedge_risk_bps=hedge_risk_bps,
    )
    net_edge = max(0.0, float(raw_edge_bps) - friction_budget_bps)
    if proof.proof_status != MarketEquivalenceProofStatus.proven:
        reason_codes.append("equivalence_not_proven")
    if proof.manual_review_required:
        reason_codes.append("proof_manual_review_required")
    if proof.mismatch_reasons:
        reason_codes.extend(proof.mismatch_reasons)
    if net_edge <= 0.0:
        reason_codes.append("non_positive_net_edge")
        manual_review_required = True
    elif net_edge < _MIN_EXECUTABLE_EDGE_BPS:
        reason_codes.append("thin_net_edge")
        manual_review_required = True
    if confidence < _MIN_EXECUTABLE_CONFIDENCE:
        reason_codes.append("low_confidence")
        manual_review_required = True
    return ExecutableEdge(
        market_ref=market_ref,
        counterparty_market_ref=counterparty_market_ref,
        proof_ref=proof.proof_id,
        raw_edge_bps=raw_edge_bps,
        fees_bps=fees_bps,
        slippage_bps=slippage_bps,
        hedge_risk_bps=hedge_risk_bps,
        executable_edge_bps=net_edge,
        confidence=confidence,
        expires_at=expires_at or (_utc_now() + timedelta(hours=6)),
        manual_review_required=manual_review_required,
        reason_codes=reason_codes,
        metadata={
            "proof_status": proof.proof_status.value,
            "proof_manual_review_required": proof.manual_review_required,
            "proof_mismatch_reasons": list(proof.mismatch_reasons),
            "resolution_compatibility": proof.resolution_compatibility,
            "payout_compatibility": proof.payout_compatibility,
            "currency_compatibility": proof.currency_compatibility,
            "timing_compatibility": proof.timing_compatibility,
            "gross_edge_bps": round(float(raw_edge_bps), 6),
            "friction_budget_bps": friction_budget_bps,
            "net_edge_margin_bps": round(net_edge - _MIN_EXECUTABLE_EDGE_BPS, 6),
            "confidence_gate": _MIN_EXECUTABLE_CONFIDENCE,
            "executable_threshold_bps": _MIN_EXECUTABLE_EDGE_BPS,
        },
    )


def build_arb_plan(
    proof: MarketEquivalenceProof,
    edge: ExecutableEdge,
    *,
    market_a: MarketDescriptor,
    market_b: MarketDescriptor,
    target_notional_usd: float,
    max_unhedged_leg_ms: int = 0,
    exit_policy: str = "close_on_edge_decay",
) -> ArbPlan:
    tradeable = proof.proof_status == MarketEquivalenceProofStatus.proven and edge.executable and edge.executable_edge_bps > 0.0
    buy_market, sell_market = _directional_markets(edge, market_a=market_a, market_b=market_b)
    legging_risk_reasons: list[str] = []
    if max_unhedged_leg_ms > 0:
        legging_risk_reasons.append(f"unhedged_leg_window:{max_unhedged_leg_ms}")
    if not tradeable:
        legging_risk_reasons.append("manual_review_required")
    legs = [
        ArbPlanLeg(
            market_ref=buy_market.market_id,
            venue=buy_market.venue,
            side=TradeSide.buy,
            position_side=TradeSide.yes,
            notional_usd=target_notional_usd,
            rationale="Enter long leg on the lower-priced side of the equivalent market pair.",
        ),
        ArbPlanLeg(
            market_ref=sell_market.market_id,
            venue=sell_market.venue,
            side=TradeSide.sell,
            position_side=TradeSide.yes,
            notional_usd=target_notional_usd,
            rationale="Offset the exposure on the higher-priced side of the equivalent market pair.",
        ),
    ]
    manual_review_required = not tradeable
    rationale = _plan_rationale_from_inputs(
        proof=proof,
        edge=edge,
        tradeable=tradeable,
        buy_market=buy_market,
        sell_market=sell_market,
        max_unhedged_leg_ms=max_unhedged_leg_ms,
    )
    return ArbPlan(
        proof_ref=proof.proof_id,
        edge_ref=edge.edge_id,
        market_a_ref=market_a.market_id,
        market_b_ref=market_b.market_id,
        canonical_event_id=proof.canonical_event_id,
        legs=legs,
        required_capital_usd=max(0.0, float(target_notional_usd) * 2.0),
        break_even_after_fees_bps=round(max(0.0, float(edge.fees_bps) + float(edge.slippage_bps) + float(edge.hedge_risk_bps)), 6),
        max_unhedged_leg_ms=max(0, int(max_unhedged_leg_ms)),
        hedge_completion_ratio=1.0 if tradeable else 0.0,
        hedge_completion_ready=bool(tradeable and max_unhedged_leg_ms == 0),
        legging_risk_reasons=legging_risk_reasons,
        exit_policy=exit_policy,
        manual_review_required=manual_review_required,
        rationale=rationale,
        metadata={
            "tradeable": tradeable,
            "proof_status": proof.proof_status.value,
            "proof_manual_review_required": proof.manual_review_required,
            "executable_edge_bps": edge.executable_edge_bps,
            "raw_edge_bps": edge.raw_edge_bps,
            "fees_bps": edge.fees_bps,
            "slippage_bps": edge.slippage_bps,
            "hedge_risk_bps": edge.hedge_risk_bps,
            "friction_budget_bps": _edge_friction_budget_bps(
                fees_bps=edge.fees_bps,
                slippage_bps=edge.slippage_bps,
                hedge_risk_bps=edge.hedge_risk_bps,
            ),
            "net_edge_margin_bps": round(float(edge.executable_edge_bps) - _MIN_EXECUTABLE_EDGE_BPS, 6),
            "executable_threshold_bps": _MIN_EXECUTABLE_EDGE_BPS,
            "max_unhedged_leg_ms": max(0, int(max_unhedged_leg_ms)),
            "legging_risk_reasons": list(legging_risk_reasons),
            "hedge_completion_ratio": 1.0 if tradeable else 0.0,
            "hedge_completion_ready": bool(tradeable and max_unhedged_leg_ms == 0),
        },
    )


def _market_resolution_source(market: MarketDescriptor) -> str | None:
    return _first_non_empty(market.resolution_source_url, market.resolution_source, market.source_url)


def _market_currency(market: MarketDescriptor) -> str | None:
    return _metadata_string(market, "currency", "settlement_currency", "collateral_currency", "payout_currency")


def _market_payout_currency(market: MarketDescriptor) -> str | None:
    return _metadata_string(market, "payout_currency", "settlement_currency", "currency", "collateral_currency")


def _resolution_compatibility(
    market_a: MarketDescriptor,
    market_b: MarketDescriptor,
    *,
    match: CrossVenueMatch | None = None,
) -> tuple[float, list[str]]:
    if match is not None:
        score = max(0.0, min(1.0, float(match.resolution_compatibility_score)))
        if score >= 0.95:
            return score, []
        return score, list(match.notes or []) or ["resolution_mismatch"]
    left = _market_resolution_source(market_a)
    right = _market_resolution_source(market_b)
    if left and right:
        if left.strip().lower() == right.strip().lower():
            return 1.0, []
        return 0.0, ["resolution_source_mismatch"]
    return 0.5, ["resolution_source_missing"]


def _payout_compatibility(
    market_a: MarketDescriptor,
    market_b: MarketDescriptor,
    *,
    match: CrossVenueMatch | None = None,
) -> tuple[float, list[str]]:
    if match is not None and match.payout_compatibility_score > 0.0:
        return max(0.0, min(1.0, float(match.payout_compatibility_score))), []
    left = _market_payout_currency(market_a)
    right = _market_payout_currency(market_b)
    if left and right:
        if left.strip().lower() == right.strip().lower():
            return 1.0, []
        return 0.0, ["payout_currency_mismatch"]
    return 0.5, ["payout_currency_missing"]


def _currency_compatibility(
    market_a: MarketDescriptor,
    market_b: MarketDescriptor,
    *,
    match: CrossVenueMatch | None = None,
) -> tuple[float, list[str]]:
    if match is not None and match.currency_compatibility_score > 0.0:
        return max(0.0, min(1.0, float(match.currency_compatibility_score))), []
    left = _market_currency(market_a)
    right = _market_currency(market_b)
    if left and right:
        if left.strip().lower() == right.strip().lower():
            return 1.0, []
        return 0.0, ["currency_mismatch"]
    return 0.5, ["currency_missing"]


def _timing_compatibility(market_a: MarketDescriptor, market_b: MarketDescriptor) -> tuple[float, list[str]]:
    left = market_a.end_date or market_a.close_time
    right = market_b.end_date or market_b.close_time
    if left and right:
        if _utc_datetime(left) == _utc_datetime(right):
            return 1.0, []
        return 0.0, ["timing_mismatch"]
    return 0.5, ["timing_missing"]


def _derive_proof_status(proof: MarketEquivalenceProof) -> MarketEquivalenceProofStatus:
    scores = [
        proof.resolution_compatibility,
        proof.payout_compatibility,
        proof.currency_compatibility,
        proof.timing_compatibility,
    ]
    if any(score == 0.0 for score in scores) and proof.mismatch_reasons:
        return MarketEquivalenceProofStatus.rejected
    if all(score >= 0.95 for score in scores) and not proof.mismatch_reasons:
        return MarketEquivalenceProofStatus.proven
    if any(reason.endswith("_missing") for reason in proof.mismatch_reasons):
        return MarketEquivalenceProofStatus.needs_review
    return MarketEquivalenceProofStatus.partial


def _proof_rationale(proof: MarketEquivalenceProof) -> str:
    if proof.proof_status == MarketEquivalenceProofStatus.proven:
        return "Markets align on resolution, payout, currency and timing."
    if proof.proof_status == MarketEquivalenceProofStatus.rejected:
        return "Markets are not equivalent enough for execution because of: " + ", ".join(proof.mismatch_reasons)
    if proof.proof_status == MarketEquivalenceProofStatus.partial:
        return "Markets are comparable but not yet clean enough for execution."
    return "Markets require manual review before execution."


def _plan_rationale_from_inputs(
    *,
    proof: MarketEquivalenceProof,
    edge: ExecutableEdge,
    tradeable: bool,
    buy_market: MarketDescriptor,
    sell_market: MarketDescriptor,
    max_unhedged_leg_ms: int = 0,
) -> str:
    friction_budget_bps = _edge_friction_budget_bps(
        fees_bps=edge.fees_bps,
        slippage_bps=edge.slippage_bps,
        hedge_risk_bps=edge.hedge_risk_bps,
    )
    base = (
        f"{buy_market.market_id} vs {sell_market.market_id}; "
        f"gross_edge_bps={edge.raw_edge_bps:.2f}; "
        f"friction_bps={friction_budget_bps:.2f}; "
        f"net_edge_bps={edge.executable_edge_bps:.2f}; "
        f"proof={proof.proof_status.value}"
    )
    if max_unhedged_leg_ms > 0:
        base += f"; legging_window_ms={max_unhedged_leg_ms}"
    if tradeable:
        return base + "; plan is tradeable under current local checks."
    return base + "; plan requires manual review or is not executable yet."


def _directional_markets(
    edge: ExecutableEdge,
    *,
    market_a: MarketDescriptor,
    market_b: MarketDescriptor,
) -> tuple[MarketDescriptor, MarketDescriptor]:
    if edge.market_ref == market_b.market_id and edge.counterparty_market_ref == market_a.market_id:
        return market_b, market_a
    return market_a, market_b
