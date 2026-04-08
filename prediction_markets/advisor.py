from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from .adapters import PolymarketAdapter, VenueAdapter
from .evidence_registry import EvidenceRegistry
from .models import (
    AdvisorArchitectureStage,
    AdvisorArchitectureSurface,
    CapitalLedgerSnapshot,
    DecisionAction,
    DecisionPacket,
    EvidencePacket,
    ExecutionReadiness,
    ForecastPacket,
    ForecastComparisonSurface,
    LedgerPosition,
    MarketDescriptor,
    MarketRecommendationPacket,
    MarketSnapshot,
    MarketStatus,
    MarketUniverseConfig,
    MarketUniverseResult,
    PaperTradeRecord,
    ReplayReport,
    ResolutionPolicy,
    ResolutionStatus,
    RunManifest,
    TradeSide,
    VenueName,
)
from .paths import PredictionMarketPaths, default_prediction_market_paths
from .registry import RunRegistryStore
from .research import ResearchCollector, build_research_abstention_metrics
from .resolution_guard import ResolutionGuard, ResolutionGuardReport, ResolutionPolicyCache
from .universe import MarketUniverse


def _surface_bridge_packet(packet: Any | None) -> dict[str, Any] | None:
    if packet is None:
        return None
    if hasattr(packet, "surface") and callable(packet.surface):
        payload = packet.surface()
    elif hasattr(packet, "model_dump"):
        payload = packet.model_dump(mode="json")
    elif isinstance(packet, dict):
        payload = dict(packet)
    else:
        payload = {"value": packet}
    if isinstance(payload, dict):
        payload.setdefault("schema_version", "v1")
        payload.setdefault("packet_version", "1.0.0")
        payload.setdefault("market_only_compatible", True)
        payload.setdefault("compatibility_mode", "market_only")
        if "packet_contract" not in payload and hasattr(packet, "contract_surface") and callable(packet.contract_surface):
            payload["packet_contract"] = packet.contract_surface()
        if "contract_id" not in payload and isinstance(payload.get("packet_contract"), dict):
            payload["contract_id"] = payload["packet_contract"].get("contract_id")
        if "packet_contract" not in payload:
            payload["packet_contract"] = {
                "contract_id": payload.get("contract_id"),
                "schema_version": payload.get("schema_version", "v1"),
                "packet_version": payload.get("packet_version", "1.0.0"),
                "packet_kind": payload.get("packet_kind", "decision"),
                "compatibility_mode": payload.get("compatibility_mode", "market_only"),
                "market_only_compatible": payload.get("market_only_compatible", True),
            }
    return payload


def _extract_bridge_probability(packet: Any | None) -> float | None:
    payload = _surface_bridge_packet(packet)
    if not isinstance(payload, dict):
        return None
    for key in ("probability_estimate", "probability_yes", "fair_probability", "confidence_low", "confidence_high", "confidence"):
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
    for nested_key in ("forecast", "decision", "metadata"):
        nested = payload.get(nested_key)
        nested_payload = _surface_bridge_packet(nested)
        if isinstance(nested_payload, dict):
            value = _extract_bridge_probability(nested_payload)
            if value is not None:
                return value
    return None


def _social_bridge_metadata(packet: Any | None) -> dict[str, Any] | None:
    payload = _surface_bridge_packet(packet)
    if not isinstance(payload, dict):
        return None
    packet_contract = payload.get("packet_contract") if isinstance(payload.get("packet_contract"), dict) else {}
    if not packet_contract and hasattr(packet, "contract_surface") and callable(packet.contract_surface):
        packet_contract = packet.contract_surface()
    return {
        "schema_version": payload.get("schema_version", "v1"),
        "packet_version": payload.get("packet_version", "1.0.0"),
        "packet_kind": payload.get("packet_kind", "decision"),
        "contract_id": payload.get("contract_id") or packet_contract.get("contract_id"),
        "packet_contract": dict(packet_contract),
        "decision_id": payload.get("decision_id"),
        "decision_action": payload.get("action"),
        "decision_confidence": payload.get("confidence"),
        "decision_probability": _extract_bridge_probability(payload),
        "source_bundle_id": payload.get("source_bundle_id"),
        "source_packet_refs": list(payload.get("source_packet_refs") or []),
        "social_context_refs": list(payload.get("social_context_refs") or []),
        "market_context_refs": list(payload.get("market_context_refs") or []),
    }


def _external_reference_source_label(evidence: EvidencePacket) -> str | None:
    metadata = dict(evidence.metadata)
    source_text = " ".join(
        part
        for part in [
            evidence.source_url,
            str(metadata.get("source_name") or ""),
            str(metadata.get("source") or ""),
            str(metadata.get("reference_source") or ""),
        ]
        if part
    ).lower()
    if "metaculus" in source_text:
        return "metaculus"
    if "manifold" in source_text:
        return "manifold"
    return None


def _external_reference_probability(evidence: EvidencePacket) -> float | None:
    metadata = dict(evidence.metadata)
    payload = metadata.get("payload") if isinstance(metadata.get("payload"), dict) else {}
    for candidate in (
        metadata.get("reference_probability_yes"),
        metadata.get("forecast_probability_yes"),
        metadata.get("market_probability_yes"),
        metadata.get("probability_yes"),
        metadata.get("probability"),
        payload.get("reference_probability_yes") if isinstance(payload, dict) else None,
        payload.get("forecast_probability_yes") if isinstance(payload, dict) else None,
        payload.get("market_probability_yes") if isinstance(payload, dict) else None,
        payload.get("probability_yes") if isinstance(payload, dict) else None,
        payload.get("probability") if isinstance(payload, dict) else None,
    ):
        if candidate is None:
            continue
        try:
            value = float(candidate)
        except (TypeError, ValueError):
            continue
        if 0.0 <= value <= 1.0:
            return round(value, 6)
    return None


def _external_reference_surface(
    evidence: list[EvidencePacket],
    *,
    market_probability_yes: float | None,
    forecast_probability_yes: float | None,
) -> dict[str, Any]:
    references: list[dict[str, Any]] = []
    for packet in evidence:
        source_label = _external_reference_source_label(packet)
        if source_label is None:
            continue
        reference_probability_yes = _external_reference_probability(packet)
        references.append({
            "reference_id": packet.evidence_id,
            "reference_source": source_label,
            "source_name": packet.metadata.get("source_name") or packet.metadata.get("source"),
            "source_url": packet.source_url,
            "source_kind": packet.source_kind.value,
            "signal_id": packet.metadata.get("signal_id") or packet.metadata.get("record_id") or packet.evidence_id,
            "captured_at": packet.observed_at,
            "reference_probability_yes": reference_probability_yes,
            "market_delta_bps": (
                round((reference_probability_yes - market_probability_yes) * 10_000.0, 2)
                if reference_probability_yes is not None and market_probability_yes is not None
                else None
            ),
            "forecast_delta_bps": (
                round((reference_probability_yes - forecast_probability_yes) * 10_000.0, 2)
                if reference_probability_yes is not None and forecast_probability_yes is not None
                else None
            ),
            "summary": packet.summary,
        })

    market_delta_values = [ref["market_delta_bps"] for ref in references if ref["market_delta_bps"] is not None]
    forecast_delta_values = [ref["forecast_delta_bps"] for ref in references if ref["forecast_delta_bps"] is not None]
    source_names = list(dict.fromkeys(
        ref["reference_source"] for ref in references if ref.get("reference_source")
    ))

    return {
        "external_references": references,
        "external_reference_count": len(references),
        "external_reference_sources": source_names,
        "market_probability_yes_hint": market_probability_yes,
        "forecast_probability_yes_hint": forecast_probability_yes,
        "market_delta_bps": round(sum(market_delta_values) / len(market_delta_values), 2) if market_delta_values else None,
        "forecast_delta_bps": round(sum(forecast_delta_values) / len(forecast_delta_values), 2) if forecast_delta_values else None,
    }


def _confidence_band_surface(low: float, high: float, center: float | None = None) -> dict[str, float]:
    center_value = center if center is not None else (low + high) / 2.0
    return {
        "low": round(max(0.0, min(1.0, low)), 6),
        "high": round(max(0.0, min(1.0, high)), 6),
        "center": round(max(0.0, min(1.0, center_value)), 6),
        "width": round(max(0.0, high - low), 6),
    }


def _market_price_reference(snapshot: MarketSnapshot) -> tuple[float | None, str | None]:
    for key, value in (
        ("market_implied_probability", snapshot.market_implied_probability),
        ("midpoint_yes", snapshot.midpoint_yes),
        ("price_yes", snapshot.price_yes),
    ):
        if value is None:
            continue
        try:
            return round(max(0.0, min(1.0, float(value))), 6), key
        except (TypeError, ValueError):
            continue
    return None, None


def _snapshot_reliability_surface(snapshot: MarketSnapshot) -> dict[str, Any]:
    price_reference, price_source = _market_price_reference(snapshot)
    has_price_proxy = price_reference is not None
    staleness_ms = snapshot.staleness_ms if snapshot.staleness_ms is not None else 0
    spread_bps = snapshot.spread_bps if snapshot.spread_bps is not None else 0.0
    liquidity = snapshot.liquidity if snapshot.liquidity is not None else 0.0
    reasons: list[str] = []
    if not has_price_proxy:
        reasons.append("missing_price_proxy")
    if liquidity <= 0:
        reasons.append("missing_liquidity")
    if staleness_ms > 120000:
        reasons.append("snapshot_stale")
    if spread_bps > 1000.0:
        reasons.append("spread_too_wide")
    reliable = not reasons
    return {
        "market_price_reference": price_reference,
        "market_price_reference_source": price_source,
        "snapshot_reliable": reliable,
        "snapshot_reliability_reasons": reasons,
        "snapshot_quality": {
            "staleness_ms": snapshot.staleness_ms,
            "spread_bps": snapshot.spread_bps,
            "liquidity": snapshot.liquidity,
            "has_orderbook": snapshot.orderbook is not None,
            "has_price_proxy": has_price_proxy,
            "reliable": reliable,
            "reliability_reasons": reasons,
        },
    }


def _market_alignment_surface(*, snapshot: MarketSnapshot, forecast: ForecastPacket, min_edge_bps: float) -> dict[str, Any]:
    reference, reference_source = _market_price_reference(snapshot)
    if reference is None:
        return {
            "market_price_reference": None,
            "market_price_reference_source": None,
            "market_price_gap_bps": None,
            "market_price_gap_abs_bps": None,
            "market_alignment": "unknown",
        }
    gap_bps = round((forecast.fair_probability - reference) * 10000.0, 2)
    abs_gap_bps = abs(gap_bps)
    if abs_gap_bps <= min(25.0, max(10.0, min_edge_bps / 2.0)):
        alignment = "aligned"
    elif abs_gap_bps <= max(150.0, min_edge_bps * 2.0):
        alignment = "actionable"
    else:
        alignment = "dislocated"
    return {
        "market_price_reference": reference,
        "market_price_reference_source": reference_source,
        "market_price_gap_bps": gap_bps,
        "market_price_gap_abs_bps": round(abs_gap_bps, 2),
        "market_alignment": alignment,
    }


def _resolution_coherence_surface(guard_report: ResolutionGuardReport) -> dict[str, Any]:
    resolution_reliable = guard_report.approved and guard_report.can_forecast and not guard_report.manual_review_required
    reliability_reasons: list[str] = []
    if guard_report.status != ResolutionStatus.clear:
        reliability_reasons.append(f"resolution_status_{guard_report.status.value}")
    if not guard_report.can_forecast:
        reliability_reasons.append("resolution_cannot_forecast")
    if guard_report.manual_review_required:
        reliability_reasons.append("resolution_manual_review_required")
    if guard_report.ambiguity_flags:
        reliability_reasons.extend(f"ambiguity:{flag}" for flag in guard_report.ambiguity_flags)
    return {
        "resolution_policy_id": guard_report.policy_id,
        "resolution_status": guard_report.status.value,
        "resolution_can_forecast": guard_report.can_forecast,
        "resolution_manual_review_required": guard_report.manual_review_required,
        "resolution_reliable": resolution_reliable,
        "resolution_reliability_reasons": reliability_reasons,
        "resolution_coherence": "clear" if resolution_reliable else ("review" if guard_report.manual_review_required else "blocked"),
    }


def _rationale_summary(rationale: str, *, fallback: str = "") -> str:
    cleaned = rationale.strip()
    if not cleaned:
        return fallback
    for separator in (". ", "; ", " - "):
        if separator in cleaned:
            return cleaned.split(separator, 1)[0].strip()
    return cleaned


def _scenario_surface(
    *,
    market_title: str,
    fair_probability: float,
    action: DecisionAction,
    fallback_action: DecisionAction | None = None,
) -> list[dict[str, Any]]:
    base_action = action.value
    fallback_value = None if fallback_action is None else fallback_action.value
    return [
        {
            "scenario": "bull",
            "summary": f"{market_title}: edge widens and the market moves toward {fair_probability:.3f}.",
            "likely_action": DecisionAction.bet.value if action == DecisionAction.bet else base_action,
        },
        {
            "scenario": "base",
            "summary": f"{market_title}: prices stay near current levels and the current guidance remains {base_action}.",
            "likely_action": fallback_value or (DecisionAction.wait.value if action == DecisionAction.wait else base_action),
        },
        {
            "scenario": "bear",
            "summary": f"{market_title}: data stays stale or resolution stays uncertain, keeping the module in {fallback_value or base_action}.",
            "likely_action": fallback_value or (DecisionAction.no_trade.value if action == DecisionAction.no_trade else base_action),
        },
    ]


def _surface_enrichment(
    *,
    market: MarketDescriptor,
    snapshot: MarketSnapshot,
    evidence: list[EvidencePacket],
    forecast: ForecastPacket,
    recommendation: MarketRecommendationPacket,
    decision: DecisionPacket,
    guard_report: ResolutionGuardReport,
    min_edge_bps: float,
    fallback_action: DecisionAction | None = None,
) -> dict[str, Any]:
    requires_manual_review = bool(
        forecast.manual_review_required
        or recommendation.action == DecisionAction.manual_review
        or decision.action == DecisionAction.manual_review
        or guard_report.manual_review_required
    )
    rationale_summary = _rationale_summary(
        forecast.rationale,
        fallback=(
            f"{market.title}: "
            f"{'insufficient market data' if fallback_action == DecisionAction.no_trade else 'hold for better data'}"
        ),
    )
    confidence_band = _confidence_band_surface(
        forecast.confidence_low,
        forecast.confidence_high,
        forecast.fair_probability,
    )
    risks = list(dict.fromkeys([*forecast.risks, *recommendation.why_not_now, *decision.why_not_now]))
    scenarios = _scenario_surface(
        market_title=market.title,
        fair_probability=forecast.fair_probability,
        action=recommendation.action,
        fallback_action=fallback_action,
    )
    external_reference_surface = _external_reference_surface(
        evidence,
        market_probability_yes=snapshot.market_implied_probability
        if snapshot.market_implied_probability is not None
        else snapshot.midpoint_yes
        if snapshot.midpoint_yes is not None
        else snapshot.price_yes,
        forecast_probability_yes=forecast.fair_probability,
    )
    snapshot_surface = _snapshot_reliability_surface(snapshot)
    alignment_surface = _market_alignment_surface(snapshot=snapshot, forecast=forecast, min_edge_bps=min_edge_bps)
    resolution_surface = _resolution_coherence_surface(guard_report)
    paper_eligible = bool(snapshot_surface["snapshot_reliable"] and resolution_surface["resolution_reliable"] and not requires_manual_review)
    return {
        "scenarios": scenarios,
        "risks": risks,
        "rationale_summary": rationale_summary,
        "confidence_band": confidence_band,
        "requires_manual_review": requires_manual_review,
        "next_review_at": forecast.next_review_at.isoformat() if forecast.next_review_at is not None else None,
        "paper_eligible": paper_eligible,
        **snapshot_surface,
        **alignment_surface,
        **resolution_surface,
        **external_reference_surface,
    }


def _build_advisor_architecture(
    *,
    run_id: str,
    market: MarketDescriptor,
    snapshot: MarketSnapshot,
    policy: ResolutionPolicy | None,
    guard_report: ResolutionGuardReport,
    evidence: list[EvidencePacket],
    forecast: ForecastPacket,
    recommendation: MarketRecommendationPacket,
    decision: DecisionPacket,
    execution_readiness: ExecutionReadiness,
    social_bridge: dict[str, Any] | None,
    backend_mode: str,
) -> AdvisorArchitectureSurface:
    resolution_status = (
        "blocked" if not guard_report.can_forecast else "degraded" if guard_report.manual_review_required else "ready"
    )
    recommendation_status = (
        "blocked"
        if recommendation.action == DecisionAction.manual_review
        else "degraded"
        if recommendation.action in {DecisionAction.wait, DecisionAction.no_trade} or recommendation.requires_manual_review
        else "ready"
    )
    decision_status = (
        "blocked"
        if decision.action == DecisionAction.manual_review
        else "degraded"
        if decision.action in {DecisionAction.wait, DecisionAction.no_trade} or decision.requires_manual_review
        else "ready"
    )
    execution_status = "ready" if execution_readiness.ready_to_execute else "blocked"
    evidence_refs = [packet.evidence_id for packet in evidence]
    return AdvisorArchitectureSurface(
        run_id=run_id,
        venue=market.venue,
        market_id=market.market_id,
        runtime="swarm",
        backend_mode=backend_mode or "auto",
        social_bridge_state="available" if social_bridge else "unavailable",
        research_bridge_state="available" if evidence_refs else "unavailable",
        packet_contracts={
            "forecast": forecast.contract_surface(),
            "recommendation": recommendation.contract_surface(),
            "decision": decision.contract_surface(),
        },
        packet_refs={
            "snapshot": snapshot.snapshot_id,
            "resolution_policy": None if policy is None else policy.policy_id,
            "forecast": forecast.forecast_id,
            "recommendation": recommendation.recommendation_id,
            "decision": decision.decision_id,
            "execution_readiness": execution_readiness.readiness_id,
        },
        stages=[
            AdvisorArchitectureStage(
                stage_id=f"{run_id}:market_context",
                stage_kind="market_context",
                role="market_data",
                status="ready",
                input_refs=[market.market_id],
                output_refs=[snapshot.snapshot_id],
                summary="Resolve the canonical market descriptor and snapshot before advisory reasoning.",
                metadata={"market_slug": market.slug, "venue_type": market.venue_type.value},
            ),
            AdvisorArchitectureStage(
                stage_id=f"{run_id}:resolution_guard",
                stage_kind="resolution_guard",
                role="guardrail",
                status=resolution_status,
                input_refs=[snapshot.snapshot_id, None if policy is None else policy.policy_id],
                output_refs=[None if policy is None else policy.policy_id],
                summary="Gate the advisor on resolution clarity before allowing forecast or execution previews.",
                metadata={
                    "manual_review_required": guard_report.manual_review_required,
                    "can_forecast": guard_report.can_forecast,
                    "reasons": list(guard_report.reasons),
                },
            ),
            AdvisorArchitectureStage(
                stage_id=f"{run_id}:research_inputs",
                stage_kind="research_inputs",
                role="evidence",
                status="ready" if evidence_refs else "skipped",
                input_refs=[market.market_id],
                output_refs=evidence_refs,
                summary="Aggregate market evidence and optional bridge context into reusable research packets.",
                metadata={
                    "evidence_count": len(evidence_refs),
                    "social_bridge_state": "available" if social_bridge else "unavailable",
                },
            ),
            AdvisorArchitectureStage(
                stage_id=f"{run_id}:forecast_packet",
                stage_kind="forecast_packet",
                role="forecast",
                status="degraded" if forecast.requires_manual_review else "ready",
                input_refs=[snapshot.snapshot_id, *evidence_refs],
                output_refs=[forecast.forecast_id],
                contract_ids=[forecast.contract_id],
                summary="Produce the canonical forecast packet used by downstream recommendation and readiness logic.",
                metadata={"social_bridge_used": forecast.social_bridge_used, "probability_estimate": forecast.probability_estimate},
            ),
            AdvisorArchitectureStage(
                stage_id=f"{run_id}:recommendation_packet",
                stage_kind="recommendation_packet",
                role="recommendation",
                status=recommendation_status,
                input_refs=[forecast.forecast_id],
                output_refs=[recommendation.recommendation_id],
                contract_ids=[recommendation.contract_id],
                summary="Translate forecast state into an operator-facing recommendation packet.",
                metadata={"action": recommendation.action.value, "side": None if recommendation.side is None else recommendation.side.value},
            ),
            AdvisorArchitectureStage(
                stage_id=f"{run_id}:decision_packet",
                stage_kind="decision_packet",
                role="decision",
                status=decision_status,
                input_refs=[forecast.forecast_id, recommendation.recommendation_id],
                output_refs=[decision.decision_id],
                contract_ids=[decision.contract_id],
                summary="Emit the canonical advisor decision packet for replay, audit, and downstream execution gates.",
                metadata={"action": decision.action.value, "confidence": decision.confidence},
            ),
            AdvisorArchitectureStage(
                stage_id=f"{run_id}:execution_readiness",
                stage_kind="execution_readiness",
                role="execution_gate",
                status=execution_status,
                input_refs=[forecast.forecast_id, recommendation.recommendation_id, decision.decision_id],
                output_refs=[execution_readiness.readiness_id],
                summary="Project the advisor result into a safe execution-readiness verdict without forcing live trading.",
                metadata={
                    "route": execution_readiness.route,
                    "risk_checks_passed": execution_readiness.risk_checks_passed,
                    "blocked_reasons": list(execution_readiness.blocked_reasons),
                },
            ),
        ],
        summary=(
            f"Reference advisor architecture for {market.market_id}: "
            "market context -> resolution guard -> research inputs -> forecast packet -> "
            "recommendation packet -> decision packet -> execution readiness."
        ),
        metadata={
            "market_title": market.title,
            "snapshot_id": snapshot.snapshot_id,
            "resolution_policy_ref": None if policy is None else policy.policy_id,
            "social_bridge_state": "available" if social_bridge else "unavailable",
        },
    )


class MarketAdviceRun(BaseModel):
    schema_version: str = "v1"
    run_id: str
    venue: VenueName
    market: MarketDescriptor
    snapshot: MarketSnapshot
    resolution_policy: ResolutionPolicy | None = None
    resolution_guard: ResolutionGuardReport
    evidence: list[EvidencePacket] = Field(default_factory=list)
    forecast: ForecastPacket
    recommendation: MarketRecommendationPacket
    decision: DecisionPacket
    execution_readiness: ExecutionReadiness
    advisor_architecture: AdvisorArchitectureSurface
    manifest: RunManifest
    manifest_path: str
    snapshot_path: str
    forecast_path: str
    recommendation_path: str
    decision_path: str
    execution_readiness_path: str
    report_path: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class MarketAdvisor:
    adapter: VenueAdapter | None = None
    paths: PredictionMarketPaths | None = None
    evidence_registry: EvidenceRegistry | None = None
    resolution_cache: ResolutionPolicyCache | None = None
    run_registry: RunRegistryStore | None = None
    fee_bps: float = 25.0
    slippage_bps: float = 40.0
    min_edge_bps: float = 35.0
    min_confidence: float = 0.55
    backend_mode: str = "auto"

    def __post_init__(self) -> None:
        self.paths = self.paths or default_prediction_market_paths()
        self.paths.ensure_layout()
        self.adapter = self.adapter or PolymarketAdapter(backend_mode=self.backend_mode)
        self.evidence_registry = self.evidence_registry or EvidenceRegistry(self.paths)
        self.resolution_cache = self.resolution_cache or ResolutionPolicyCache(self.paths)
        self.run_registry = self.run_registry or RunRegistryStore(self.paths)
        self._research = ResearchCollector(venue=VenueName.polymarket)
        self._guard = ResolutionGuard(self.resolution_cache)
        self._universe = MarketUniverse(adapter=self.adapter)

    def discover_markets(self, *, query: str | None = None, limit: int = 25) -> list[MarketDescriptor]:
        config = None
        if query is not None:
            config = MarketUniverseConfig(query=query, limit=limit, venue=VenueName.polymarket)
        result = self._universe.discover(config)
        return result.markets

    def advise(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        evidence_notes: list[str] | None = None,
        extra_evidence: list[EvidencePacket] | None = None,
        decision_packet: Any | None = None,
        use_social_core: bool = False,
        persist: bool = True,
        record_evidence: bool = True,
        run_id: str | None = None,
        mode: str = "advise",
    ) -> MarketAdviceRun:
        market = self._resolve_market(market_id=market_id, slug=slug)
        advice_run_id = run_id or f"pm_{market.market_id}_{uuid4().hex[:8]}"
        snapshot = self.adapter.get_snapshot(market.market_id)
        policy = self.adapter.get_resolution_policy(market.market_id)
        guard_report = self._guard.evaluate(market, policy=policy, snapshot=snapshot)

        evidence = list(extra_evidence or [])
        if evidence_notes:
            evidence.extend(
                self._research.from_notes(
                    market_id=market.market_id,
                    notes=evidence_notes,
                    run_id=advice_run_id,
                )
            )
        if not evidence:
            evidence.extend(self.adapter.get_evidence(market.market_id))

        social_bridge = _social_bridge_metadata(decision_packet)
        research_pipeline = self._research.build_pipeline(
            evidence,
            market_id=market.market_id,
            run_id=advice_run_id,
            snapshot=snapshot,
            retrieval_policy="evidence_packets",
            input_count=len(evidence_notes or []),
            evidence_count=len(evidence),
            applied=False,
        )
        research_abstention_policy = research_pipeline.abstention_policy
        research_signal_applied = not research_abstention_policy.abstain
        research_abstention_metrics = build_research_abstention_metrics(
            research_pipeline,
            applied=research_signal_applied,
        )
        if record_evidence:
            for item in evidence:
                self.evidence_registry.add(item)

        forecast = self._build_forecast(
            run_id=advice_run_id,
            market=market,
            snapshot=snapshot,
            policy=policy,
            guard_report=guard_report,
            evidence=evidence,
            decision_packet=decision_packet,
            use_social_core=use_social_core,
            research_signal_applied=research_signal_applied,
        )
        recommendation = self._build_recommendation(
            advice_run_id,
            market,
            snapshot,
            forecast,
            evidence,
            decision_packet=decision_packet,
        )
        decision = self._build_decision(
            advice_run_id,
            market,
            forecast,
            recommendation,
            evidence,
            decision_packet=decision_packet,
        )
        surface_enrichment = _surface_enrichment(
            market=market,
            snapshot=snapshot,
            evidence=evidence,
            forecast=forecast,
            recommendation=recommendation,
            decision=decision,
            guard_report=guard_report,
            min_edge_bps=self.min_edge_bps,
            fallback_action=forecast.recommendation_action if forecast.recommendation_action in {DecisionAction.wait, DecisionAction.no_trade} else None,
        )
        surface_enrichment.update(
            {
                "research_pipeline": research_pipeline.model_dump(mode="json"),
                "research_abstention_policy": research_abstention_policy.model_dump(mode="json"),
                "research_abstention_metrics": research_abstention_metrics,
                "research_public_metrics": dict(research_pipeline.public_metrics),
                "research_signal_applied": research_signal_applied,
            }
        )
        forecast = forecast.model_copy(
            update={
                "metadata": {
                    **dict(forecast.metadata),
                    **surface_enrichment,
                }
            }
        )
        recommendation = recommendation.model_copy(
            update={
                "metadata": {
                    **dict(recommendation.metadata),
                    **surface_enrichment,
                }
            }
        )
        decision = decision.model_copy(
            update={
                "metadata": {
                    **dict(decision.metadata),
                    **surface_enrichment,
                }
            }
        )
        execution_readiness = self._build_execution_readiness(
            run_id=advice_run_id,
            market=market,
            forecast=forecast,
            recommendation=recommendation,
            decision=decision,
            guard_report=guard_report,
            evidence=evidence,
            mode=mode,
        )
        advisor_architecture = _build_advisor_architecture(
            run_id=advice_run_id,
            market=market,
            snapshot=snapshot,
            policy=policy,
            guard_report=guard_report,
            evidence=evidence,
            forecast=forecast,
            recommendation=recommendation,
            decision=decision,
            execution_readiness=execution_readiness,
            social_bridge=social_bridge,
            backend_mode=self.backend_mode,
        )
        manifest = RunManifest(
            run_id=advice_run_id,
            venue=market.venue,
            venue_type=market.venue_type,
            market_id=market.market_id,
            mode=mode,
            inputs={
                "market_id": market.market_id,
                "slug": market.slug,
                "evidence_notes": evidence_notes or [],
                "backend_mode": self.backend_mode,
                "fee_bps": self.fee_bps,
                "slippage_bps": self.slippage_bps,
                "min_edge_bps": self.min_edge_bps,
                "min_confidence": self.min_confidence,
            },
            snapshot_ref=f"snapshot:{snapshot.snapshot_id}",
            resolution_policy_ref=f"policy:{policy.policy_id}" if policy else None,
            evidence_refs=[item.evidence_id for item in evidence],
            forecast_ref=forecast.forecast_id,
            recommendation_ref=recommendation.recommendation_id,
            decision_ref=decision.decision_id,
            execution_readiness_ref=execution_readiness.readiness_id,
            metadata={
                "market_title": market.title,
                "resolution_guard": guard_report.model_dump(mode="json"),
                "backend_mode": self.backend_mode,
                "social_bridge": social_bridge,
                "advisor_architecture": advisor_architecture.model_dump(mode="json"),
                **surface_enrichment,
            },
        )

        if persist:
            return self._persist_run(
                run_id=advice_run_id,
                market=market,
                snapshot=snapshot,
                policy=policy,
                guard_report=guard_report,
                evidence=evidence,
                forecast=forecast,
                recommendation=recommendation,
                decision=decision,
                execution_readiness=execution_readiness,
                advisor_architecture=advisor_architecture,
                manifest=manifest,
                mode=mode,
                social_bridge=social_bridge,
            )

        return MarketAdviceRun(
            run_id=advice_run_id,
            venue=market.venue,
            market=market,
            snapshot=snapshot,
            resolution_policy=policy,
            resolution_guard=guard_report,
            evidence=evidence,
            forecast=forecast,
            recommendation=recommendation,
            decision=decision,
            execution_readiness=execution_readiness,
            advisor_architecture=advisor_architecture,
            manifest=manifest,
            manifest_path="",
            snapshot_path="",
            forecast_path="",
            recommendation_path="",
            decision_path="",
            execution_readiness_path="",
            report_path="",
            metadata={
                "persisted": False,
                "social_bridge": social_bridge,
                "advisor_architecture": advisor_architecture.model_dump(mode="json"),
                **surface_enrichment,
            },
        )

    def paper_trade(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        evidence_notes: list[str] | None = None,
        extra_evidence: list[EvidencePacket] | None = None,
        stake: float = 10.0,
        persist: bool = True,
        run_id: str | None = None,
        mode: str = "paper",
    ) -> dict[str, Any]:
        payload = self.advise(
            market_id=market_id,
            slug=slug,
            evidence_notes=evidence_notes,
            extra_evidence=extra_evidence,
            persist=persist,
            run_id=run_id,
            mode=mode,
        )
        recommendation = payload.recommendation
        snapshot = payload.snapshot
        paper = PaperTradeRecord(
            run_id=payload.run_id,
            market_id=payload.market.market_id,
            action=recommendation.action,
            side=recommendation.side,
            size=stake,
            entry_price=recommendation.price_reference,
            status="proposed" if recommendation.action != DecisionAction.no_trade else "skipped",
            metadata={"edge_bps": recommendation.edge_bps, "confidence": recommendation.confidence, "midpoint_yes": snapshot.midpoint_yes},
        )
        if persist:
            assert self.paths is not None
            self.paths.ensure_layout()
            paper_path = self.paths.paper_trade_path(paper.trade_id)
            paper_path.write_text(paper.model_dump_json(indent=2), encoding="utf-8")
            payload.metadata["paper_trade_path"] = str(paper_path)
        return {
            **payload.model_dump(mode="json"),
            "paper_trade": paper.model_dump(mode="json"),
        }

    def forecast_market(
        self,
        market_id: str | None = None,
        *,
        slug: str | None = None,
        evidence_notes: list[str] | None = None,
        extra_evidence: list[EvidencePacket] | None = None,
        decision_packet: Any | None = None,
        use_social_core: bool = False,
        persist: bool = True,
        record_evidence: bool = False,
        run_id: str | None = None,
        mode: str = "forecast",
    ) -> dict[str, Any]:
        forecast_run_id = run_id or f"pm_{slug or market_id or 'market'}_{uuid4().hex[:8]}"
        baseline_run = self.advise(
            market_id=market_id,
            slug=slug,
            evidence_notes=evidence_notes,
            extra_evidence=extra_evidence,
            decision_packet=decision_packet,
            use_social_core=False,
            persist=False,
            record_evidence=record_evidence,
            run_id=forecast_run_id,
            mode=mode,
        )
        enriched_run = baseline_run
        if use_social_core:
            enriched_run = self.advise(
                market_id=market_id,
                slug=slug,
                evidence_notes=evidence_notes,
                extra_evidence=extra_evidence,
                decision_packet=decision_packet,
                use_social_core=True,
                persist=False,
                record_evidence=record_evidence,
                run_id=forecast_run_id,
                mode=mode,
            )
        bridge = _social_bridge_metadata(decision_packet)
        comparison = ForecastComparisonSurface(
            run_id=forecast_run_id,
            market_id=baseline_run.market.market_id,
            venue=baseline_run.market.venue,
            social_core_used=use_social_core,
            base_forecast_id=baseline_run.forecast.forecast_id,
            social_forecast_id=enriched_run.forecast.forecast_id if use_social_core else None,
            base_probability_estimate=baseline_run.forecast.fair_probability,
            social_probability_estimate=enriched_run.forecast.fair_probability,
            base_edge_after_fees_bps=baseline_run.forecast.edge_after_fees_bps,
            social_edge_after_fees_bps=enriched_run.forecast.edge_after_fees_bps,
            base_recommendation_action=baseline_run.forecast.recommendation_action,
            social_recommendation_action=enriched_run.forecast.recommendation_action,
            base_requires_manual_review=baseline_run.forecast.manual_review_required,
            social_requires_manual_review=enriched_run.forecast.manual_review_required,
            social_bridge_probability=enriched_run.forecast.social_bridge_probability,
            social_bridge_delta_bps=enriched_run.forecast.social_bridge_delta_bps,
            social_bridge_refs=list((bridge or {}).get("source_packet_refs") or []),
            metadata={
                "market_title": baseline_run.market.title,
                "baseline_recommendation": baseline_run.recommendation.recommendation if baseline_run.recommendation else None,
                "social_recommendation": enriched_run.recommendation.recommendation if enriched_run.recommendation else None,
                "use_social_core": use_social_core,
                "social_bridge": bridge,
                "baseline_confidence_band": baseline_run.forecast.confidence_band,
                "social_confidence_band": enriched_run.forecast.confidence_band,
            },
        )
        payload: dict[str, Any] = {
            "run_id": forecast_run_id,
            "market": baseline_run.market,
            "snapshot": baseline_run.snapshot,
            "baseline_forecast": baseline_run.forecast,
            "social_forecast": enriched_run.forecast,
            "baseline_recommendation": baseline_run.recommendation,
            "social_recommendation": enriched_run.recommendation,
            "comparison": comparison,
            "decision_packet": decision_packet,
            "use_social_core": use_social_core,
        }
        if persist and self.paths is not None:
            run_dir = self.paths.run_dir(forecast_run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            comparison_path = run_dir / "forecast_comparison.json"
            comparison_path.write_text(comparison.model_dump_json(indent=2), encoding="utf-8")
            payload["comparison_path"] = str(comparison_path)
        return payload

    def ledger_snapshot(self, run_id: str, *, cash: float, reserved_cash: float = 0.0) -> CapitalLedgerSnapshot:
        return CapitalLedgerSnapshot(
            venue=VenueName.polymarket,
            cash=cash,
            reserved_cash=reserved_cash,
            equity=cash - reserved_cash,
            positions=[],
            metadata={"run_id": run_id},
        )

    def _resolve_market(self, *, market_id: str | None, slug: str | None) -> MarketDescriptor:
        if market_id:
            return self.adapter.get_market(market_id)
        if slug:
            markets = self.adapter.list_markets(limit=250)
            for market in markets:
                if market.slug == slug:
                    return market
        raise KeyError(f"Unknown market identifier: market_id={market_id!r} slug={slug!r}")

    def _persist_run(
        self,
        *,
        run_id: str,
        market: MarketDescriptor,
        snapshot: MarketSnapshot,
        policy: ResolutionPolicy | None,
        guard_report: ResolutionGuardReport,
        evidence: list[EvidencePacket],
        forecast: ForecastPacket,
        recommendation: MarketRecommendationPacket,
        decision: DecisionPacket,
        execution_readiness: ExecutionReadiness,
        advisor_architecture: AdvisorArchitectureSurface,
        manifest: RunManifest,
        mode: str,
        social_bridge: dict[str, Any] | None,
    ) -> MarketAdviceRun:
        assert self.paths is not None
        run_dir = self.paths.run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = self.paths.snapshot_path(run_id)
        forecast_path = self.paths.forecast_path(run_id)
        recommendation_path = self.paths.recommendation_path(run_id)
        decision_path = self.paths.decision_path(run_id)
        execution_readiness_path = run_dir / "execution_readiness.json"
        advisor_architecture_path = run_dir / "advisor_architecture.json"
        report_path = self.paths.report_path(run_id)
        manifest_path = self.paths.run_manifest_path(run_id)

        snapshot_path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
        forecast_path.write_text(forecast.model_dump_json(indent=2), encoding="utf-8")
        recommendation_path.write_text(recommendation.model_dump_json(indent=2), encoding="utf-8")
        decision_path.write_text(decision.model_dump_json(indent=2), encoding="utf-8")
        execution_readiness.persist(execution_readiness_path)
        advisor_architecture.persist(advisor_architecture_path)

        report = MarketAdviceRun(
            run_id=run_id,
            venue=market.venue,
            market=market,
            snapshot=snapshot,
            resolution_policy=policy,
            resolution_guard=guard_report,
            evidence=evidence,
            forecast=forecast,
            recommendation=recommendation,
            decision=decision,
            execution_readiness=execution_readiness,
            advisor_architecture=advisor_architecture,
            manifest=manifest,
            manifest_path=str(manifest_path),
            snapshot_path=str(snapshot_path),
            forecast_path=str(forecast_path),
            recommendation_path=str(recommendation_path),
            decision_path=str(decision_path),
            execution_readiness_path=str(execution_readiness_path),
            report_path=str(report_path),
            metadata={
                "persisted": True,
                "mode": mode,
                "social_bridge": social_bridge,
                "advisor_architecture": advisor_architecture.model_dump(mode="json"),
                **dict(manifest.metadata),
            },
        )
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        manifest.forecast_ref = str(forecast_path)
        manifest.recommendation_ref = str(recommendation_path)
        manifest.decision_ref = str(decision_path)
        manifest.execution_readiness_ref = execution_readiness.readiness_id
        manifest.artifact_refs = [
            str(snapshot_path),
            str(forecast_path),
            str(recommendation_path),
            str(decision_path),
            str(execution_readiness_path),
            str(advisor_architecture_path),
            str(report_path),
        ]
        manifest.artifact_paths = {
            "snapshot": str(snapshot_path),
            "forecast": str(forecast_path),
            "recommendation": str(recommendation_path),
            "decision": str(decision_path),
            "execution_readiness": str(execution_readiness_path),
            "advisor_architecture": str(advisor_architecture_path),
            "report": str(report_path),
        }
        manifest.touch()
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        self.run_registry.record_manifest(manifest, manifest_path=manifest_path)
        return report

    def _build_forecast(
        self,
        *,
        run_id: str,
        market: MarketDescriptor,
        snapshot: MarketSnapshot,
        policy: ResolutionPolicy | None,
        guard_report: ResolutionGuardReport,
        evidence: list[EvidencePacket],
        decision_packet: Any | None = None,
        use_social_core: bool = False,
        research_signal_applied: bool | None = None,
    ) -> ForecastPacket:
        implied = snapshot.market_implied_probability
        price_proxy_missing = implied is None and snapshot.midpoint_yes is None and snapshot.price_yes is None and snapshot.orderbook is None
        weak_data_proxy = snapshot.market_implied_probability is None and snapshot.midpoint_yes is None
        if implied is None:
            implied = self._fallback_probability(snapshot, market)
        apply_research_signal = True if research_signal_applied is None else bool(research_signal_applied)
        evidence_bias = self._evidence_bias(evidence) if apply_research_signal else 0.0
        ambiguity_penalty = 0.12 if guard_report.manual_review_required or guard_report.status != ResolutionStatus.clear else 0.0
        liquidity_adjustment = 0.0 if snapshot.liquidity is None else min(0.03, snapshot.liquidity / 2_000_000.0)
        base_fair_probability = max(0.0, min(1.0, implied + evidence_bias + liquidity_adjustment - ambiguity_penalty))
        bridge_probability = _extract_bridge_probability(decision_packet)
        social_bridge_used = bool(use_social_core and bridge_probability is not None)
        fair_probability = base_fair_probability
        if social_bridge_used and bridge_probability is not None:
            blend_weight = 0.35
            fair_probability = max(
                0.0,
                min(1.0, base_fair_probability * (1.0 - blend_weight) + bridge_probability * blend_weight),
            )
        spread = snapshot.spread_bps or 100.0
        staleness_ms = snapshot.staleness_ms or 0
        confidence_width = min(0.25, 0.08 + (spread / 10000.0) * 0.4 + min(0.12, staleness_ms / 120000.0))
        confidence_low = max(0.0, fair_probability - confidence_width)
        confidence_high = min(1.0, fair_probability + confidence_width)
        confidence_score = max(0.0, min(1.0, 1.0 - confidence_width))
        edge_bps = round((fair_probability - implied) * 10000.0, 2)
        edge_after_fees_bps = round(edge_bps - self.fee_bps - (snapshot.spread_bps or 0.0) * 0.2 - self.slippage_bps, 2)
        social_bridge_delta_bps = round((fair_probability - base_fair_probability) * 10000.0, 2) if social_bridge_used else None
        manual_review_required = guard_report.manual_review_required or guard_report.status != ResolutionStatus.clear or not guard_report.can_forecast
        fallback_action: DecisionAction | None = None
        if price_proxy_missing or weak_data_proxy:
            if not evidence or snapshot.liquidity is None:
                fallback_action = DecisionAction.no_trade
            else:
                fallback_action = DecisionAction.wait
        elif snapshot.staleness_ms is not None and snapshot.staleness_ms > 120000:
            fallback_action = DecisionAction.wait
        action = self._decision_from_metrics(
            edge_after_fees_bps=edge_after_fees_bps,
            confidence_score=confidence_score,
            manual_review_required=manual_review_required,
        )
        if fallback_action is not None and not manual_review_required:
            action = fallback_action
        rationale = self._build_rationale(
            market=market,
            snapshot=snapshot,
            evidence=evidence,
            implied=implied,
            fair_probability=fair_probability,
            edge_after_fees_bps=edge_after_fees_bps,
            guard_report=guard_report,
        )
        risks = list(dict.fromkeys(guard_report.reasons + [f"spread_bps={snapshot.spread_bps or 0.0:.2f}", f"staleness_ms={snapshot.staleness_ms or 0}"]))
        snapshot_reliability = _snapshot_reliability_surface(snapshot)
        resolution_reliability = _resolution_coherence_surface(guard_report)
        if price_proxy_missing:
            risks.append("missing_price_proxy")
        if weak_data_proxy:
            risks.append("missing_midpoint_proxy")
        if snapshot.liquidity is None:
            risks.append("missing_liquidity")
        if not evidence:
            risks.append("no_evidence_packets")
        elif not apply_research_signal:
            risks.append("research_abstained")
        if not snapshot_reliability["snapshot_reliable"]:
            risks.append("snapshot_unreliable")
            risks.extend(f"snapshot_unreliable:{reason}" for reason in snapshot_reliability["snapshot_reliability_reasons"])
        if not resolution_reliability["resolution_reliable"]:
            risks.append("resolution_unreliable")
            risks.extend(f"resolution_unreliable:{reason}" for reason in resolution_reliability["resolution_reliability_reasons"])
        if fallback_action is not None:
            risks.append(f"fallback_action={fallback_action.value}")
        resolution_policy_missing = policy is None
        return ForecastPacket(
            run_id=run_id,
            market_id=market.market_id,
            venue=market.venue,
            market_implied_probability=implied,
            fair_probability=fair_probability,
            confidence_low=confidence_low,
            confidence_high=confidence_high,
            edge_bps=edge_bps,
            edge_after_fees_bps=edge_after_fees_bps,
            recommendation_action=action,
            manual_review_required=manual_review_required,
            rationale=rationale,
            risks=risks,
            evidence_refs=[item.evidence_id for item in evidence],
            resolution_policy_ref=policy.policy_id if policy else None,
            resolution_policy_id=policy.policy_id if policy else None,
            snapshot_id=snapshot.snapshot_id,
            model_used="rule_based_v1",
            calibration_notes=list(guard_report.ambiguity_flags),
            social_bridge_used=social_bridge_used,
            social_bridge_probability=bridge_probability if social_bridge_used else None,
            social_bridge_delta_bps=social_bridge_delta_bps,
            social_bridge_mode=str((_social_bridge_metadata(decision_packet) or {}).get("packet_kind") or "decision") if social_bridge_used else None,
            metadata={
                "market_title": market.title,
                "market_status": market.status.value,
                "backend_mode": self.backend_mode,
                "confidence_score": confidence_score,
                "decision_probability": bridge_probability,
                "evidence_count": len(evidence),
                "research_signal_applied": apply_research_signal,
                "social_bridge": _social_bridge_metadata(decision_packet),
                "social_bridge_used": social_bridge_used,
                "social_bridge_probability": bridge_probability if social_bridge_used else None,
                "social_bridge_delta_bps": social_bridge_delta_bps,
                "social_bridge_mode": str((_social_bridge_metadata(decision_packet) or {}).get("packet_kind") or "decision") if social_bridge_used else None,
                "resolution_policy_missing": resolution_policy_missing,
                "confidence_band": _confidence_band_surface(confidence_low, confidence_high, fair_probability),
                "requires_manual_review": manual_review_required,
                "rationale_summary": _rationale_summary(
                    rationale,
                    fallback=f"{market.title}: {'no trade' if action == DecisionAction.no_trade else 'wait'} for better data.",
                ),
                "scenarios": _scenario_surface(
                    market_title=market.title,
                    fair_probability=fair_probability,
                    action=action,
                    fallback_action=fallback_action,
                ),
                "fallback_action": None if fallback_action is None else fallback_action.value,
                "research_signal_applied": bool(research_signal_applied),
            },
        )

    def _build_recommendation(
        self,
        run_id: str,
        market: MarketDescriptor,
        snapshot: MarketSnapshot,
        forecast: ForecastPacket,
        evidence: list[EvidencePacket],
        decision_packet: Any | None = None,
    ) -> MarketRecommendationPacket:
        action = forecast.recommendation_action
        side = None
        if action == DecisionAction.bet:
            side = TradeSide.yes if forecast.fair_probability >= forecast.market_implied_probability else TradeSide.no
        price_reference = (
            snapshot.market_implied_probability
            if snapshot.market_implied_probability is not None
            else snapshot.midpoint_yes
            if snapshot.midpoint_yes is not None
            else 0.5
        )
        why_now = [
            f"Forecast fair probability={forecast.fair_probability:.3f} vs implied={forecast.market_implied_probability:.3f}",
            f"Net edge after fees={forecast.edge_after_fees_bps:.2f} bps",
        ]
        why_not_now = list(forecast.risks)
        watch_conditions = []
        if forecast.manual_review_required:
            watch_conditions.append("resolution_guard_clearance")
        if forecast.edge_after_fees_bps < self.min_edge_bps:
            watch_conditions.append("edge_widens")
        if (snapshot.staleness_ms or 0) > 120000:
            watch_conditions.append("fresh_snapshot")
        human_summary = self._human_summary(market, action, side, forecast)
        return MarketRecommendationPacket(
            run_id=run_id,
            forecast_id=forecast.forecast_id,
            market_id=market.market_id,
            venue=market.venue,
            action=action,
            side=side,
            price_reference=price_reference,
            edge_bps=forecast.edge_after_fees_bps,
            why_now=why_now,
            why_not_now=why_not_now,
            watch_conditions=watch_conditions,
            human_summary=human_summary,
            confidence=max(0.0, min(1.0, 1.0 - ((forecast.confidence_high - forecast.confidence_low) / 2.0))),
            artifact_refs=list(forecast.evidence_refs),
            social_bridge_used=forecast.social_bridge_used,
            social_bridge_probability=forecast.social_bridge_probability,
            social_bridge_delta_bps=forecast.social_bridge_delta_bps,
            social_bridge_mode=forecast.social_bridge_mode,
            resolution_policy_ref=forecast.resolution_policy_ref,
            metadata={
                "evidence_count": len(evidence),
                "social_bridge": forecast.metadata.get("social_bridge") or _social_bridge_metadata(decision_packet),
                "social_bridge_used": forecast.social_bridge_used,
                "social_bridge_probability": forecast.social_bridge_probability,
                "social_bridge_delta_bps": forecast.social_bridge_delta_bps,
                "social_bridge_mode": forecast.social_bridge_mode,
                "requires_manual_review": forecast.manual_review_required,
                "resolution_policy_missing": forecast.resolution_policy_missing,
                "rationale_summary": _rationale_summary(
                    forecast.rationale,
                    fallback=f"{market.title}: wait for better data.",
                ),
                "confidence_band": _confidence_band_surface(forecast.confidence_low, forecast.confidence_high, forecast.fair_probability),
                "scenarios": _scenario_surface(
                    market_title=market.title,
                    fair_probability=forecast.fair_probability,
                    action=action,
                    fallback_action=action if action in {DecisionAction.wait, DecisionAction.no_trade} else None,
                ),
                "risks": list(dict.fromkeys(forecast.risks + why_not_now)),
            },
        )

    def _build_decision(
        self,
        run_id: str,
        market: MarketDescriptor,
        forecast: ForecastPacket,
        recommendation: MarketRecommendationPacket,
        evidence: list[EvidencePacket],
        decision_packet: Any | None = None,
    ) -> DecisionPacket:
        return DecisionPacket(
            run_id=run_id,
            market_id=market.market_id,
            venue=market.venue,
            action=recommendation.action,
            confidence=recommendation.confidence,
            summary=recommendation.human_summary,
            rationale=forecast.rationale,
            why_now=list(recommendation.why_now),
            why_not_now=list(recommendation.why_not_now),
            watch_conditions=list(recommendation.watch_conditions),
            evidence_refs=[item.evidence_id for item in evidence],
            social_bridge_used=forecast.social_bridge_used,
            social_bridge_probability=forecast.social_bridge_probability,
            social_bridge_delta_bps=forecast.social_bridge_delta_bps,
            social_bridge_mode=forecast.social_bridge_mode,
            resolution_policy_ref=forecast.resolution_policy_ref,
            metadata={
                "forecast_id": forecast.forecast_id,
                "recommendation_id": recommendation.recommendation_id,
                "social_bridge": forecast.metadata.get("social_bridge") or _social_bridge_metadata(decision_packet),
                "social_bridge_used": forecast.social_bridge_used,
                "social_bridge_probability": forecast.social_bridge_probability,
                "social_bridge_delta_bps": forecast.social_bridge_delta_bps,
                "social_bridge_mode": forecast.social_bridge_mode,
                "requires_manual_review": forecast.manual_review_required or recommendation.action == DecisionAction.manual_review,
                "resolution_policy_missing": forecast.resolution_policy_missing,
                "rationale_summary": _rationale_summary(
                    forecast.rationale,
                    fallback=f"{market.title}: wait for better data.",
                ),
                "confidence_band": _confidence_band_surface(forecast.confidence_low, forecast.confidence_high, forecast.fair_probability),
                "scenarios": _scenario_surface(
                    market_title=market.title,
                    fair_probability=forecast.fair_probability,
                    action=recommendation.action,
                    fallback_action=recommendation.action if recommendation.action in {DecisionAction.wait, DecisionAction.no_trade} else None,
                ),
                "risks": list(dict.fromkeys(forecast.risks + recommendation.why_not_now)),
            },
        )

    def _build_execution_readiness(
        self,
        *,
        run_id: str,
        market: MarketDescriptor,
        forecast: ForecastPacket,
        recommendation: MarketRecommendationPacket,
        decision: DecisionPacket,
        guard_report: ResolutionGuardReport,
        evidence: list[EvidencePacket],
        mode: str,
    ) -> ExecutionReadiness:
        advisory_notes = list(
            dict.fromkeys(
                [
                    *forecast.risks,
                    *recommendation.why_not_now,
                    *decision.why_not_now,
                    *guard_report.reasons,
                ]
            )
        )
        blocked_reasons: list[str] = []
        if forecast.manual_review_required:
            blocked_reasons.append("forecast_manual_review_required")
        if decision.action == DecisionAction.manual_review:
            blocked_reasons.append("decision_manual_review")
        if decision.action in {DecisionAction.no_trade, DecisionAction.wait}:
            blocked_reasons.append(f"decision_action={decision.action.value}")
        if recommendation.side is None and decision.action == DecisionAction.bet:
            blocked_reasons.append("missing_trade_side")
        if recommendation.price_reference is None:
            blocked_reasons.append("missing_price_reference")
        confidence = recommendation.confidence
        edge_after_fees_bps = forecast.edge_after_fees_bps
        risk_checks_passed = (
            decision.action == DecisionAction.bet
            and recommendation.side is not None
            and recommendation.price_reference is not None
            and edge_after_fees_bps >= self.min_edge_bps
            and confidence >= self.min_confidence
            and not guard_report.manual_review_required
            and guard_report.can_forecast
        )
        if not risk_checks_passed:
            blocked_reasons.append("risk_checks_failed")
        suggested_size_usd = 0.0
        if risk_checks_passed:
            edge_weight = max(0.0, edge_after_fees_bps) / 10.0
            confidence_weight = max(0.25, confidence)
            suggested_size_usd = round(min(100.0, max(5.0, edge_weight) * confidence_weight), 2)
        route = "paper" if risk_checks_passed else "blocked"
        execution_notes = [
            f"mode={mode}",
            f"evidence_count={len(evidence)}",
            f"confidence={confidence:.3f}",
            f"edge_after_fees_bps={edge_after_fees_bps:.2f}",
            f"advisory_notes={len(advisory_notes)}",
        ]
        if not blocked_reasons and not risk_checks_passed:
            blocked_reasons.append("insufficient_readiness")
        return ExecutionReadiness(
            run_id=run_id,
            market_id=market.market_id,
            venue=market.venue,
            decision_id=decision.decision_id,
            forecast_id=forecast.forecast_id,
            recommendation_id=recommendation.recommendation_id,
            decision_action=decision.action,
            side=recommendation.side,
            size_usd=suggested_size_usd,
            limit_price=recommendation.price_reference,
            max_slippage_bps=max(self.slippage_bps, 0.0),
            confidence=confidence,
            edge_after_fees_bps=edge_after_fees_bps,
            risk_checks_passed=risk_checks_passed,
            manual_review_required=forecast.manual_review_required or guard_report.manual_review_required,
            resolution_policy_ref=forecast.resolution_policy_ref,
            blocked_reasons=blocked_reasons,
            no_trade_reasons=list(blocked_reasons) if blocked_reasons else [],
            route=route,
            execution_notes=execution_notes,
            metadata={
                "market_title": market.title,
                "evidence_count": len(evidence),
                "resolution_status": guard_report.status.value,
                "backend_mode": self.backend_mode,
                "live_gate_passed": False,
                "advisory_notes": advisory_notes,
                "resolution_policy_missing": forecast.resolution_policy_missing,
            },
        )

    def _decision_from_metrics(
        self,
        *,
        edge_after_fees_bps: float,
        confidence_score: float,
        manual_review_required: bool,
    ) -> DecisionAction:
        if manual_review_required:
            return DecisionAction.manual_review
        if confidence_score < self.min_confidence or edge_after_fees_bps < self.min_edge_bps:
            if edge_after_fees_bps <= -self.min_edge_bps:
                return DecisionAction.no_trade
            return DecisionAction.wait
        return DecisionAction.bet

    @staticmethod
    def _fallback_probability(snapshot: MarketSnapshot, market: MarketDescriptor) -> float:
        if snapshot.midpoint_yes is not None:
            return snapshot.midpoint_yes
        if snapshot.orderbook and snapshot.orderbook.mid_probability is not None:
            return snapshot.orderbook.mid_probability
        if market.liquidity:
            return min(0.75, max(0.25, market.clarity_score))
        return 0.5

    @staticmethod
    def _evidence_bias(evidence: list[EvidencePacket]) -> float:
        bias = 0.0
        for item in evidence:
            stance = item.stance.lower()
            sign = 0.0
            if "bull" in stance or "yes" in stance or stance in {"positive", "support"}:
                sign = 1.0
            elif "bear" in stance or "no" in stance or stance in {"negative", "oppose"}:
                sign = -1.0
            weight = item.evidence_weight * 0.12
            bias += sign * weight
        return max(-0.18, min(0.18, bias))

    @staticmethod
    def _build_rationale(
        *,
        market: MarketDescriptor,
        snapshot: MarketSnapshot,
        evidence: list[EvidencePacket],
        implied: float,
        fair_probability: float,
        edge_after_fees_bps: float,
        guard_report: ResolutionGuardReport,
    ) -> str:
        evidence_phrase = f"{len(evidence)} evidence packet(s)"
        if evidence:
            strongest = max(evidence, key=lambda item: item.evidence_weight)
            evidence_phrase += f", strongest='{strongest.claim[:80]}'"
        return (
            f"{market.title}: implied={implied:.3f}, fair={fair_probability:.3f}, "
            f"net_edge_after_fees={edge_after_fees_bps:.2f}bps, "
            f"snapshot_staleness={snapshot.staleness_ms or 0}ms, "
            f"resolution_status={guard_report.status.value}, {evidence_phrase}."
        )

    @staticmethod
    def _human_summary(market: MarketDescriptor, action: DecisionAction, side: TradeSide | None, forecast: ForecastPacket) -> str:
        if action == DecisionAction.bet and side is not None:
            return f"{market.title}: take a {side.value.upper()} position; forecast edge is {forecast.edge_after_fees_bps:.2f} bps."
        if action == DecisionAction.manual_review:
            return f"{market.title}: manual review required before any position."
        if action == DecisionAction.wait:
            return f"{market.title}: wait for better edge or fresher data."
        return f"{market.title}: no trade recommended at current prices."


def build_default_market_advisor(*, backend_mode: str = "auto", base_dir: str | Path | None = None) -> MarketAdvisor:
    paths = PredictionMarketPaths(root=Path(base_dir)) if base_dir is not None else None
    return MarketAdvisor(paths=paths, backend_mode=backend_mode)
