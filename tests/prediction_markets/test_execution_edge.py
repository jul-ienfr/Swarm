from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from prediction_markets.execution_edge import (
    ArbPlan,
    ExecutableEdge,
    MarketEquivalenceProof,
    MarketEquivalenceProofStatus,
    assess_market_equivalence,
    build_arb_plan,
    derive_executable_edge,
)
from prediction_markets.models import MarketDescriptor, MarketStatus, TradeSide, VenueName, VenueType


def _market(
    market_id: str,
    *,
    canonical_event_id: str,
    resolution_source_url: str,
    end_date: datetime,
    currency: str = "USD",
    payout_currency: str = "USD",
) -> MarketDescriptor:
    return MarketDescriptor(
        market_id=market_id,
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        title=f"Market {market_id}",
        question="Will the test event happen?",
        canonical_event_id=canonical_event_id,
        event_id=canonical_event_id,
        resolution_source_url=resolution_source_url,
        open_time=end_date - timedelta(days=1),
        end_date=end_date,
        liquidity=5000.0,
        volume_24h=1000.0,
        status=MarketStatus.open,
        metadata={
            "currency": currency,
            "payout_currency": payout_currency,
            "settlement_currency": currency,
        },
    )


def test_market_equivalence_proof_can_be_proven_and_persisted(tmp_path) -> None:
    end_date = datetime(2026, 4, 9, 0, 0, tzinfo=timezone.utc)
    left = _market(
        "pm_left",
        canonical_event_id="event_1",
        resolution_source_url="https://example.com/resolution",
        end_date=end_date,
    )
    right = _market(
        "pm_right",
        canonical_event_id="event_1",
        resolution_source_url="https://example.com/resolution",
        end_date=end_date,
    )

    proof = assess_market_equivalence(left, right)
    persisted = proof.persist(tmp_path / "proof.json")
    loaded = MarketEquivalenceProof.load(persisted)

    assert proof.proof_status == MarketEquivalenceProofStatus.proven
    assert proof.manual_review_required is False
    assert proof.resolution_compatibility == pytest.approx(1.0)
    assert proof.payout_compatibility == pytest.approx(1.0)
    assert proof.currency_compatibility == pytest.approx(1.0)
    assert proof.timing_compatibility == pytest.approx(1.0)
    assert proof.mismatch_reasons == []
    assert proof.content_hash
    assert loaded.content_hash == proof.content_hash
    assert loaded.proof_status == MarketEquivalenceProofStatus.proven


def test_market_equivalence_proof_detects_mismatches() -> None:
    left = _market(
        "pm_left",
        canonical_event_id="event_1",
        resolution_source_url="https://example.com/resolution-a",
        end_date=datetime(2026, 4, 9, 0, 0, tzinfo=timezone.utc),
        currency="USD",
        payout_currency="USD",
    )
    right = _market(
        "pm_right",
        canonical_event_id="event_1",
        resolution_source_url="https://example.com/resolution-b",
        end_date=datetime(2026, 4, 10, 0, 0, tzinfo=timezone.utc),
        currency="EUR",
        payout_currency="EUR",
    )

    proof = assess_market_equivalence(left, right)

    assert proof.proof_status == MarketEquivalenceProofStatus.rejected
    assert proof.manual_review_required is True
    assert "resolution_source_mismatch" in proof.mismatch_reasons
    assert "currency_mismatch" in proof.mismatch_reasons
    assert "payout_currency_mismatch" in proof.mismatch_reasons
    assert "timing_mismatch" in proof.mismatch_reasons


def test_executable_edge_and_arb_plan_are_derived_consistently(tmp_path) -> None:
    end_date = datetime(2026, 4, 9, 0, 0, tzinfo=timezone.utc)
    left = _market(
        "pm_left",
        canonical_event_id="event_1",
        resolution_source_url="https://example.com/resolution",
        end_date=end_date,
    )
    right = _market(
        "pm_right",
        canonical_event_id="event_1",
        resolution_source_url="https://example.com/resolution",
        end_date=end_date,
    )

    proof = assess_market_equivalence(left, right)
    edge = derive_executable_edge(
        proof,
        market_ref=left.market_id,
        counterparty_market_ref=right.market_id,
        raw_edge_bps=210.0,
        fees_bps=30.0,
        slippage_bps=20.0,
        hedge_risk_bps=10.0,
        confidence=0.8,
        expires_at=datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
    )
    plan = build_arb_plan(
        proof,
        edge,
        market_a=left,
        market_b=right,
        target_notional_usd=1000.0,
        max_unhedged_leg_ms=2500,
    )

    persisted = plan.persist(tmp_path / "arb_plan.json")
    loaded = ArbPlan.load(persisted)

    assert edge.executable_edge_bps == pytest.approx(150.0)
    assert edge.executable is True
    assert edge.manual_review_required is False
    assert edge.content_hash
    assert edge.metadata["friction_budget_bps"] == pytest.approx(60.0)
    assert edge.metadata["net_edge_margin_bps"] == pytest.approx(130.0)
    assert plan.manual_review_required is False
    assert plan.executable is True
    assert plan.required_capital_usd == pytest.approx(2000.0)
    assert plan.break_even_after_fees_bps == pytest.approx(60.0)
    assert plan.max_unhedged_leg_ms == 2500
    assert plan.hedge_completion_ratio == pytest.approx(1.0)
    assert plan.hedge_completion_ready is False
    assert "unhedged_leg_window:2500" in plan.legging_risk_reasons
    assert "legging_window_ms=2500" in plan.rationale
    assert plan.exit_policy == "close_on_edge_decay"
    assert len(plan.legs) == 2
    assert plan.legs[0].market_ref == left.market_id
    assert plan.legs[0].side == TradeSide.buy
    assert plan.legs[1].market_ref == right.market_id
    assert plan.legs[1].side == TradeSide.sell
    assert loaded.content_hash == plan.content_hash


def test_executable_edge_flags_unprofitable_or_uncertain_edges() -> None:
    left = _market(
        "pm_left",
        canonical_event_id="event_1",
        resolution_source_url="https://example.com/resolution",
        end_date=datetime(2026, 4, 9, 0, 0, tzinfo=timezone.utc),
    )
    right = _market(
        "pm_right",
        canonical_event_id="event_1",
        resolution_source_url="https://example.com/resolution",
        end_date=datetime(2026, 4, 9, 0, 0, tzinfo=timezone.utc),
    )

    proof = assess_market_equivalence(left, right)
    edge = derive_executable_edge(
        proof,
        market_ref=left.market_id,
        counterparty_market_ref=right.market_id,
        raw_edge_bps=40.0,
        fees_bps=30.0,
        slippage_bps=15.0,
        hedge_risk_bps=10.0,
        confidence=0.3,
    )

    assert edge.executable_edge_bps == pytest.approx(0.0)
    assert edge.manual_review_required is True
    assert edge.executable is False
    assert "non_positive_net_edge" in edge.reason_codes
    assert "low_confidence" in edge.reason_codes


def test_executable_edge_blocks_thin_positive_margin_edges() -> None:
    left = _market(
        "pm_left",
        canonical_event_id="event_1",
        resolution_source_url="https://example.com/resolution",
        end_date=datetime(2026, 4, 9, 0, 0, tzinfo=timezone.utc),
    )
    right = _market(
        "pm_right",
        canonical_event_id="event_1",
        resolution_source_url="https://example.com/resolution",
        end_date=datetime(2026, 4, 9, 0, 0, tzinfo=timezone.utc),
    )

    proof = assess_market_equivalence(left, right)
    edge = derive_executable_edge(
        proof,
        market_ref=left.market_id,
        counterparty_market_ref=right.market_id,
        raw_edge_bps=79.0,
        fees_bps=20.0,
        slippage_bps=25.0,
        hedge_risk_bps=15.0,
        confidence=0.72,
    )

    assert edge.executable_edge_bps == pytest.approx(19.0)
    assert edge.manual_review_required is True
    assert edge.executable is False
    assert "thin_net_edge" in edge.reason_codes
    assert edge.metadata["friction_budget_bps"] == pytest.approx(60.0)
    assert edge.metadata["net_edge_margin_bps"] == pytest.approx(-1.0)
