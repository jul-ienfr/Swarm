from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .adapters import _capability_metadata, _event_markets, _load_position_records
from .models import (
    EvidencePacket,
    LedgerPosition,
    MarketDescriptor,
    MarketOrderBook,
    MarketSnapshot,
    MarketStatus,
    MarketUniverseConfig,
    OrderBookLevel,
    ResolutionPolicy,
    ResolutionStatus,
    SourceKind,
    TradeRecord,
    TradeSide,
    VenueCapabilitiesModel,
    VenueHealthReport,
    VenueName,
    VenueType,
)
from .registry import VenueRoleClassification


class AdditionalVenueKind(str, Enum):
    signal = "signal"
    reference = "reference"
    execution_like = "execution_like"
    watchlist = "watchlist"


def _manual_execution_mode_for_pathway(pathway: str) -> str:
    return {
        "live_execution": "live",
        "bounded_execution": "bounded",
        "execution_bindable_dry_run": "dry_run_adapter",
        "execution_like_dry_run": "dry_run_adapter",
        "execution_like_paper_only": "paper_only",
        "dry_run_only": "dry_run_only",
        "reference_read_only": "reference_only",
        "signal_read_only": "signal_only",
        "watchlist_read_only": "watchlist_only",
    }.get(pathway, "read_only")


def _operator_action_for_pathway(pathway: str) -> str:
    return {
        "live_execution": "route_live_orders",
        "bounded_execution": "route_bounded_orders",
        "execution_bindable_dry_run": "run_dry_run_adapter",
        "execution_like_dry_run": "run_dry_run_adapter",
        "execution_like_paper_only": "paper_trade_only",
        "dry_run_only": "run_dry_run_adapter",
        "reference_read_only": "consume_reference_only",
        "signal_read_only": "consume_signal_only",
        "watchlist_read_only": "monitor_watchlist_only",
    }.get(pathway, "no_order_routing")


def _readiness_stage_for_pathway(pathway: str) -> str:
    return {
        "live_execution": "live_ready",
        "bounded_execution": "bounded_ready",
        "execution_bindable_dry_run": "bindable_ready",
        "execution_like_dry_run": "dry_run_ready",
        "dry_run_only": "dry_run_ready",
        "execution_like_paper_only": "paper_ready",
        "reference_read_only": "read_only",
        "signal_read_only": "read_only",
        "watchlist_read_only": "read_only",
    }.get(pathway, "read_only")


def _promotion_ladder_step(
    *,
    pathway: str,
    current_pathway: str,
    promotion_target_pathway: str | None,
    promotion_rules_by_pathway: dict[str, list[str]],
    next_pathway_rules: list[str],
    blocked_pathways: list[str],
) -> dict[str, Any]:
    return {
        "pathway": pathway,
        "manual_execution_mode": _manual_execution_mode_for_pathway(pathway),
        "readiness_stage": _readiness_stage_for_pathway(pathway),
        "operator_action": _operator_action_for_pathway(pathway),
        "promotion_target_pathway": promotion_target_pathway if pathway == current_pathway else None,
        "promotion_rules": list(promotion_rules_by_pathway.get(pathway, [])),
        "is_current": pathway == current_pathway,
        "is_blocked": pathway in blocked_pathways,
        "next_pathway_rules": list(next_pathway_rules if pathway == promotion_target_pathway else []),
    }


def _manual_execution_contract_for_profile(profile: "AdditionalVenueProfile") -> dict[str, Any]:
    current_pathway = profile.execution_pathway()
    promotion_target_pathway = profile.promotion_target_pathway()
    promotion_rules_by_pathway = profile.promotion_rules_by_pathway()
    next_pathway = profile.next_pathway()
    next_pathway_rules = profile.next_pathway_rules()
    blocked_pathways = profile.blocked_pathways()
    promotion_steps = [
        _promotion_ladder_step(
            pathway=pathway,
            current_pathway=current_pathway,
            promotion_target_pathway=promotion_target_pathway,
            promotion_rules_by_pathway=promotion_rules_by_pathway,
            next_pathway_rules=next_pathway_rules,
            blocked_pathways=blocked_pathways,
        )
        for pathway in profile.pathway_ladder()
    ]
    return {
        "current_pathway": current_pathway,
        "manual_execution_mode": _manual_execution_mode_for_pathway(current_pathway),
        "operator_action": profile.required_operator_action(),
        "manual_route_kind": _manual_execution_mode_for_pathway(current_pathway),
        "allows_dry_run_routing": current_pathway in {"execution_bindable_dry_run", "execution_like_dry_run", "dry_run_only"},
        "allows_bounded_order_routing": current_pathway == "bounded_execution",
        "allows_live_order_routing": current_pathway == "live_execution",
        "requires_promotion": current_pathway in {"execution_bindable_dry_run", "execution_like_dry_run", "execution_like_paper_only", "dry_run_only"},
        "promotion_target_pathway": promotion_target_pathway,
        "promotion_rules_by_pathway": {key: list(value) for key, value in promotion_rules_by_pathway.items()},
        "next_pathway": next_pathway,
        "next_pathway_rules": list(next_pathway_rules),
        "pathway_ladder": list(profile.pathway_ladder()),
        "blocked_pathways": list(blocked_pathways),
        "promotion_steps": promotion_steps,
    }


class AdditionalVenueProfile(BaseModel):
    schema_version: str = "v1"
    venue: VenueName
    kind: AdditionalVenueKind = AdditionalVenueKind.signal
    backend_mode: str = "bootstrap"
    bootstrap_tier: str = "tier_b"
    bootstrap_role: str = "bootstrap"
    default_venue_type: VenueType = VenueType.reference
    qualified_venue_types: set[VenueType] = Field(default_factory=set)
    source_url: str | None = None
    capabilities: VenueCapabilitiesModel
    planned_order_types: list[str] = Field(default_factory=list)
    supported_order_types: list[str] = Field(default_factory=list)
    descriptors: list[MarketDescriptor] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def descriptor_ids(self) -> list[str]:
        return [descriptor.market_id for descriptor in self.descriptors]

    def qualifies_for(self, venue_type: VenueType) -> bool:
        if venue_type == self.default_venue_type:
            return True
        return venue_type in self.qualified_venue_types

    def role_labels(self) -> list[str]:
        roles = set(self.qualified_venue_types)
        roles.add(self.default_venue_type)
        return [role.value for role in _ordered_venue_types(roles)]

    def tradeability_class(self) -> str:
        value = self.metadata.get("tradeability_class") or self.capabilities.metadata_map.get("tradeability_class")
        if value:
            return str(value)
        if self.default_venue_type == VenueType.execution:
            return "execution_bindable_dry_run" if self.execution_bindable_supported() else "execution_like_paper_only"
        if self.default_venue_type == VenueType.reference:
            return "reference_paper_only"
        if self.default_venue_type == VenueType.signal:
            return "signal_paper_only"
        return "watchlist_paper_only"

    def execution_taxonomy(self) -> str:
        value = self.metadata.get("execution_taxonomy") or self.capabilities.metadata_map.get("execution_taxonomy")
        if value:
            return str(value)
        if self.live_execution_supported():
            return "execution_ready"
        if self.bounded_execution_supported():
            return "execution_equivalent"
        if self.execution_bindable_supported():
            return "execution_bindable"
        return "execution_like"

    def venue_taxonomy(self) -> str:
        value = self.metadata.get("venue_taxonomy") or self.capabilities.metadata_map.get("venue_taxonomy")
        if value:
            return str(value)
        return self.kind.value

    def live_execution_supported(self) -> bool:
        capability_metadata = dict(self.capabilities.metadata_map or {})
        return bool(
            self.metadata.get("live_execution_supported", False)
            or self.metadata.get("live_execution_available", False)
            or capability_metadata.get("live_execution_supported", False)
            or capability_metadata.get("live_execution_available", False)
        )

    def execution_bindable_supported(self) -> bool:
        capability_metadata = dict(self.capabilities.metadata_map or {})
        planned_order_types = self.planned_order_types or list(capability_metadata.get("planned_order_types", []))
        route_supported = bool(capability_metadata.get("route_supported", True))
        return bool(
            self.backend_mode == "bootstrap"
            and self.kind == AdditionalVenueKind.execution_like
            and route_supported
            and self.capabilities.supports_paper_mode
            and planned_order_types
        )

    def bounded_execution_supported(self) -> bool:
        capability_metadata = dict(self.capabilities.metadata_map or {})
        return bool(
            self.metadata.get("bounded_execution_supported", False)
            or self.metadata.get("bounded_execution_available", False)
            or capability_metadata.get("bounded_execution_supported", False)
            or capability_metadata.get("bounded_execution_available", False)
            or self.metadata.get("market_execution_supported", False)
            or capability_metadata.get("market_execution_supported", False)
        )

    def execution_pathway(self) -> str:
        if self.backend_mode != "bootstrap" and self.live_execution_supported():
            return "live_execution"
        if self.backend_mode != "bootstrap" and self.bounded_execution_supported():
            return "bounded_execution"
        if self.execution_bindable_supported():
            return "execution_bindable_dry_run"
        if self.kind == AdditionalVenueKind.execution_like:
            return "execution_like_paper_only"
        if self.kind == AdditionalVenueKind.reference:
            return "reference_read_only"
        if self.kind == AdditionalVenueKind.signal:
            return "signal_read_only"
        return "watchlist_read_only"

    def pathway_modes(self) -> list[str]:
        modes: list[str] = []
        if self.backend_mode == "bootstrap" and self.capabilities.metadata_map.get("paper_capable", False):
            modes.append("paper")
        if self.execution_bindable_supported():
            modes.append("dry_run")
        if self.backend_mode != "bootstrap" and self.bounded_execution_supported():
            modes.append("bounded_live")
        if self.backend_mode != "bootstrap" and self.live_execution_supported():
            modes.append("live")
        return list(dict.fromkeys(modes))

    def highest_actionable_mode(self) -> str | None:
        modes = self.pathway_modes()
        return modes[-1] if modes else None

    def required_operator_action(self) -> str:
        pathway = self.execution_pathway()
        if pathway == "live_execution":
            return "route_live_orders"
        if pathway == "bounded_execution":
            return "route_bounded_orders"
        if pathway == "execution_bindable_dry_run":
            return "run_dry_run_adapter"
        if pathway == "execution_like_paper_only":
            return "paper_trade_only"
        if pathway == "reference_read_only":
            return "consume_reference_only"
        if pathway == "signal_read_only":
            return "consume_signal_only"
        if pathway == "watchlist_read_only":
            return "monitor_watchlist_only"
        return "no_order_routing"

    def promotion_target_pathway(self) -> str | None:
        pathway = self.execution_pathway()
        if pathway in {"execution_like_paper_only", "execution_bindable_dry_run"}:
            return "bounded_execution"
        if pathway == "bounded_execution":
            return "live_execution"
        return None

    def promotion_rules(self) -> list[str]:
        target = self.promotion_target_pathway()
        if target == "bounded_execution":
            return [
                "prove_bounded_execution_adapter",
                "prove_cancel_order_path",
                "prove_fill_audit",
            ]
        if target == "live_execution":
            return [
                "prove_live_execution_adapter",
                "prove_live_cancel_path",
                "prove_live_fill_audit",
                "prove_compliance_gates",
            ]
        return []

    def promotion_ladder(self) -> list[dict[str, Any]]:
        return list(self.manual_execution_contract().get("promotion_steps", []))

    def manual_execution_contract(self) -> dict[str, Any]:
        return _manual_execution_contract_for_profile(self)

    def pathway_ladder(self) -> list[str]:
        pathway = self.execution_pathway()
        if pathway == "live_execution":
            return ["live_execution"]
        if pathway == "bounded_execution":
            return ["bounded_execution", "live_execution"]
        if pathway == "execution_bindable_dry_run":
            return ["execution_bindable_dry_run", "bounded_execution", "live_execution"]
        if pathway == "execution_like_paper_only":
            return ["execution_like_paper_only", "execution_bindable_dry_run", "bounded_execution", "live_execution"]
        return [pathway]

    def blocked_pathways(self) -> list[str]:
        ladder = self.pathway_ladder()
        return ladder[1:]

    def readiness_stage(self) -> str:
        highest_mode = self.highest_actionable_mode()
        if highest_mode == "live":
            return "live_ready"
        if highest_mode == "bounded_live":
            return "bounded_ready"
        if highest_mode == "dry_run":
            return "bindable_ready" if self.execution_bindable_supported() else "dry_run_ready"
        if highest_mode == "paper":
            return "paper_ready"
        return "read_only"

    def next_pathway(self) -> str | None:
        blocked = self.blocked_pathways()
        return blocked[0] if blocked else None

    def next_pathway_rules(self) -> list[str]:
        next_pathway = self.next_pathway()
        if not next_pathway:
            return []
        return list(self.promotion_rules_by_pathway().get(next_pathway, []))

    def bounded_execution_equivalent(self) -> bool:
        return self.execution_pathway() in {"bounded_execution", "live_execution"}

    def bounded_execution_promotion_candidate(self) -> bool:
        return (not self.bounded_execution_equivalent()) and "bounded_execution" in self.blocked_pathways()

    def credential_gate(self) -> str:
        pathway = self.execution_pathway()
        if pathway == "live_execution":
            return "live_credentials_required"
        if pathway == "bounded_execution":
            return "bounded_credentials_required"
        if pathway in {"execution_bindable_dry_run", "execution_like_paper_only"}:
            return "not_required_current_mode"
        return "read_only"

    def api_gate(self) -> str:
        api_access = set(self.capabilities.metadata_map.get("api_access", []))
        pathway = self.execution_pathway()
        route_supported = bool(self.capabilities.metadata_map.get("route_supported", True))
        if pathway in {"live_execution", "bounded_execution"}:
            return "order_api_available" if "orders" in api_access else "order_api_missing"
        if pathway == "execution_bindable_dry_run":
            return "dry_run_order_api_available" if route_supported and self.capabilities.supports_paper_mode else "dry_run_order_api_missing"
        if pathway == "execution_like_paper_only":
            return "planning_only_no_order_api"
        if pathway == "reference_read_only":
            return "reference_only_surface"
        if pathway == "signal_read_only":
            return "signal_only_surface"
        return "watchlist_only_surface"

    def adapter_readiness(self) -> dict[str, bool]:
        return {
            "paper_mode_ready": "paper" in self.pathway_modes(),
            "dry_run_adapter_ready": self.execution_pathway() == "execution_bindable_dry_run",
            "bounded_execution_adapter_ready": self.execution_pathway() == "bounded_execution" or self.bounded_execution_supported(),
            "live_execution_adapter_ready": self.execution_pathway() == "live_execution" or self.live_execution_supported(),
            "cancel_path_ready": False,
            "fill_audit_ready": bool(self.capabilities.metadata_map.get("supports_trades", self.capabilities.supports_trades)),
            "order_ack_ready": self.execution_pathway() == "execution_bindable_dry_run",
        }

    def execution_requirement_codes(self) -> list[str]:
        pathway = self.execution_pathway()
        if pathway == "live_execution":
            return [
                "live_execution_adapter",
                "supported_order_types",
                "cancel_order_path",
                "fill_audit",
                "credentials",
                "compliance",
            ]
        if pathway == "bounded_execution":
            return [
                "bounded_execution_adapter",
                "supported_order_types",
                "cancel_order_path",
                "fill_audit",
            ]
        if pathway == "execution_bindable_dry_run":
            return [
                "dry_run_adapter",
                "dry_run_order_ack",
                "planned_order_types",
            ]
        if pathway == "execution_like_paper_only":
            return [
                "paper_mode",
                "bootstrap_descriptors",
            ]
        if pathway == "reference_read_only":
            return ["reference_surface"]
        if pathway == "signal_read_only":
            return ["signal_surface"]
        return ["watchlist_surface"]

    def missing_requirement_codes(self) -> list[str]:
        blocker_map = {
            "execution_like_paper_only": "dry_run_adapter",
            "execution_bindable_dry_run": "dry_run_adapter",
            "no_live_execution_adapter": "live_execution_adapter",
            "no_bounded_execution_adapter": "bounded_execution_adapter",
            "planned_order_types_only": "supported_order_types",
            "no_live_websocket": "market_feed_api",
            "no_trade_surface": "trade_surface",
            "execution_unsupported": "execution_api",
            "reference_only": "reference_surface",
            "signal_only": "signal_surface",
            "watchlist_only": "watchlist_surface",
        }
        missing = [
            blocker_map[code]
            for code in self.execution_blocker_codes()
            if code in blocker_map
        ]
        return list(dict.fromkeys(missing))

    def operator_checklist(self) -> list[str]:
        checklist = [f"action:{self.required_operator_action()}"]
        checklist.extend(f"gate:{code}" for code in self.missing_requirement_codes())
        checklist.extend(f"promote:{rule}" for rule in self.next_pathway_rules())
        if self.credential_gate() != "not_required_current_mode":
            checklist.append(f"credentials:{self.credential_gate()}")
        checklist.append(f"api:{self.api_gate()}")
        return list(dict.fromkeys(checklist))

    def promotion_evidence_by_pathway(self) -> dict[str, dict[str, Any]]:
        evidence: dict[str, dict[str, Any]] = {}
        current_pathway = self.execution_pathway()
        for pathway in self.pathway_ladder():
            required_rules = list(self.promotion_rules_by_pathway().get(pathway, []))
            status = "current" if pathway == current_pathway else "blocked"
            evidence[pathway] = {
                "status": status,
                "required_evidence": required_rules,
                "missing_evidence": list(required_rules if status == "blocked" else []),
                "evidence_count": len(required_rules),
            }
        return evidence

    def stage_summary(self) -> dict[str, Any]:
        pathway_ladder = self.pathway_ladder()
        blocked_pathways = self.blocked_pathways()
        next_pathway = self.next_pathway()
        next_pathway_rules = self.next_pathway_rules()
        manual_execution_contract = self.manual_execution_contract()
        promotion_ladder = self.promotion_ladder()
        adapter_readiness = self.adapter_readiness()
        execution_requirement_codes = self.execution_requirement_codes()
        missing_requirement_codes = self.missing_requirement_codes()
        operator_summary = self.operator_checklist()[0] if self.operator_checklist() else "action:no_order_routing"
        pathway_summary = (
            f"pathway={self.execution_pathway()} | readiness={self.readiness_stage()} | "
            f"next={next_pathway or 'none'} | blocked={','.join(blocked_pathways) if blocked_pathways else 'none'}"
        )
        promotion_summary = (
            f"promote->{self.promotion_target_pathway() or 'none'} | "
            f"rules={len(self.promotion_rules())} | "
            f"current_mode={self.highest_actionable_mode() or 'none'}"
        )
        blocker_summary = ", ".join(blocked_pathways) if blocked_pathways else "none"
        return {
            "execution_pathway": self.execution_pathway(),
            "current_pathway": self.execution_pathway(),
            "readiness_stage": self.readiness_stage(),
            "highest_actionable_mode": self.highest_actionable_mode(),
            "pathway_summary": pathway_summary,
            "operator_summary": operator_summary,
            "promotion_summary": promotion_summary,
            "blocker_summary": blocker_summary,
            "required_operator_action": self.required_operator_action(),
            "credential_gate": self.credential_gate(),
            "api_gate": self.api_gate(),
            "adapter_readiness": adapter_readiness,
            "execution_requirement_codes": execution_requirement_codes,
            "missing_requirement_codes": missing_requirement_codes,
            "missing_requirement_count": len(missing_requirement_codes),
            "operator_checklist": self.operator_checklist(),
            "next_pathway": next_pathway,
            "next_pathway_rules": next_pathway_rules,
            "next_pathway_rule_count": len(next_pathway_rules),
            "promotion_evidence_by_pathway": self.promotion_evidence_by_pathway(),
            "bounded_execution_equivalent": self.bounded_execution_equivalent(),
            "bounded_execution_promotion_candidate": self.bounded_execution_promotion_candidate(),
            "operator_ready_now": self.highest_actionable_mode() is not None,
            "pathway_ladder": pathway_ladder,
            "pathway_count": len(pathway_ladder),
            "blocked_pathways": blocked_pathways,
            "blocked_pathway_count": len(blocked_pathways),
            "remaining_pathways": blocked_pathways,
            "remaining_pathway_count": len(blocked_pathways),
            "manual_execution_contract": dict(manual_execution_contract),
            "promotion_ladder": [dict(step) for step in promotion_ladder],
        }

    def promotion_rules_by_pathway(self) -> dict[str, list[str]]:
        rules_by_pathway: dict[str, list[str]] = {}
        for pathway in self.blocked_pathways():
            if pathway == "execution_bindable_dry_run":
                rules_by_pathway[pathway] = [
                    "prove_dry_run_submit_path",
                    "prove_order_ack_path",
                    "prove_supported_order_types",
                ]
            elif pathway == "bounded_execution":
                rules_by_pathway[pathway] = [
                    "prove_bounded_execution_adapter",
                    "prove_cancel_order_path",
                    "prove_fill_audit",
                ]
            elif pathway == "live_execution":
                rules_by_pathway[pathway] = [
                    "prove_live_execution_adapter",
                    "prove_live_cancel_path",
                    "prove_live_fill_audit",
                    "prove_compliance_gates",
                ]
        return rules_by_pathway

    def execution_blocker_codes(self) -> list[str]:
        blockers: list[str] = []
        live_supported = self.live_execution_supported()
        bounded_supported = self.bounded_execution_supported()
        if self.capabilities.read_only:
            blockers.append("read_only_bootstrap")
        if not self.capabilities.execution:
            blockers.append("execution_unsupported")
        if self.kind == AdditionalVenueKind.execution_like:
            blockers.append("execution_bindable_only")
            if not live_supported:
                blockers.append("no_live_execution_adapter")
            if not bounded_supported:
                blockers.append("no_bounded_execution_adapter")
        elif self.kind == AdditionalVenueKind.reference:
            blockers.append("reference_only")
        elif self.kind == AdditionalVenueKind.signal:
            blockers.append("signal_only")
        elif self.kind == AdditionalVenueKind.watchlist:
            blockers.append("watchlist_only")
        if self.kind == AdditionalVenueKind.execution_like and self.planned_order_types and not self.supported_order_types:
            blockers.append("planned_order_types_only")
        if not self.capabilities.supports_websocket:
            blockers.append("no_live_websocket")
        if not self.capabilities.supports_trades:
            blockers.append("no_trade_surface")
        return list(dict.fromkeys(blockers))


class AdditionalVenueSurface(BaseModel):
    schema_version: str = "v1"
    venue: VenueName
    kind: AdditionalVenueKind
    backend_mode: str
    bootstrap_tier: str
    bootstrap_role: str
    default_venue_type: VenueType
    planning_bucket: str
    status: str
    execution_readiness: str = "read_only"
    execution_role: str = "watchlist_only"
    execution_pathway: str = "watchlist_read_only"
    execution_equivalent: bool = False
    read_only: bool
    paper_capable: bool
    execution_capable: bool
    pathway_modes: list[str] = Field(default_factory=list)
    highest_actionable_mode: str | None = None
    readiness_stage: str = "read_only"
    required_operator_action: str = "no_order_routing"
    promotion_target_pathway: str | None = None
    promotion_rules: list[str] = Field(default_factory=list)
    pathway_ladder: list[str] = Field(default_factory=list)
    blocked_pathways: list[str] = Field(default_factory=list)
    promotion_rules_by_pathway: dict[str, list[str]] = Field(default_factory=dict)
    next_pathway: str | None = None
    next_pathway_rules: list[str] = Field(default_factory=list)
    bounded_execution_equivalent: bool = False
    bounded_execution_promotion_candidate: bool = False
    stage_summary: dict[str, Any] = Field(default_factory=dict)
    planned_order_types: list[str] = Field(default_factory=list)
    supported_order_types: list[str] = Field(default_factory=list)
    positions_capable: bool
    events_capable: bool
    supports_market_feed: bool = False
    supports_user_feed: bool = False
    supports_rtds: bool = False
    tradeability_class: str = "read_only"
    venue_taxonomy: str = ""
    execution_taxonomy: str = "execution_like"
    execution_blocker_codes: list[str] = Field(default_factory=list)
    role_labels: list[str] = Field(default_factory=list)
    capability_notes: dict[str, Any] = Field(default_factory=dict)
    runbook: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VenueCapabilityMatrix(BaseModel):
    schema_version: str = "v1"
    profiles: list[AdditionalVenueProfile] = Field(default_factory=list)

    def profile(self, venue: VenueName) -> AdditionalVenueProfile | None:
        for profile in self.profiles:
            if profile.venue == venue:
                return profile
        return None

    def venues(self) -> list[VenueName]:
        return [profile.venue for profile in self.profiles]

    def venues_supporting(self, feature: str) -> list[VenueName]:
        supported: list[VenueName] = []
        for profile in self.profiles:
            if _feature_supported(profile.capabilities, feature):
                supported.append(profile.venue)
        return supported

    def read_only_venues(self) -> list[VenueName]:
        return [profile.venue for profile in self.profiles if profile.capabilities.read_only]

    def paper_capable_venues(self) -> list[VenueName]:
        return self.venues_supporting("paper_capable")

    def execution_capable_venues(self) -> list[VenueName]:
        return self.venues_supporting("execution_capable")

    def positions_capable_venues(self) -> list[VenueName]:
        return self.venues_supporting("positions_capable")

    def events_capable_venues(self) -> list[VenueName]:
        return self.venues_supporting("events_capable")

    def paper_execution_like_venues(self) -> list[VenueName]:
        return [
            profile.venue
            for profile in self.profiles
            if profile.tradeability_class() in {"execution_like_paper_only", "execution_bindable_dry_run"}
        ]

    def execution_bindable_venues(self) -> list[VenueName]:
        return [
            profile.venue
            for profile in self.profiles
            if profile.execution_taxonomy() == "execution_bindable"
        ]

    def venues_for_bootstrap_role(self, bootstrap_role: str) -> list[VenueName]:
        normalized = str(bootstrap_role).strip().lower()
        return [
            profile.venue
            for profile in self.profiles
            if profile.bootstrap_role.strip().lower() == normalized
        ]

    def venues_for_taxonomy(self, venue_taxonomy: str) -> list[VenueName]:
        normalized = str(venue_taxonomy).strip().lower()
        return [
            profile.venue
            for profile in self.profiles
            if profile.venue_taxonomy().strip().lower() == normalized
        ]

    def tradeability_map(self) -> dict[str, str]:
        return {profile.venue.value: profile.tradeability_class() for profile in self.profiles}

    def qualifies_for(self, venue: VenueName, venue_type: VenueType) -> bool:
        profile = self.profile(venue)
        if profile is None:
            return False
        return profile.qualifies_for(venue_type)

    def venues_for_role(self, venue_type: VenueType) -> list[VenueName]:
        venues = [profile.venue for profile in self.profiles if profile.qualifies_for(venue_type)]
        return venues

    def execution_venues(self) -> list[VenueName]:
        return self.venues_for_role(VenueType.execution)

    def execution_equivalent_venues(self) -> list[VenueName]:
        return [profile.venue for profile in self.profiles if self._execution_equivalent_for_profile(profile)]

    def reference_venues(self) -> list[VenueName]:
        return self.venues_for_role(VenueType.reference)

    def reference_only_venues(self) -> list[VenueName]:
        return self.reference_venues()

    def signal_venues(self) -> list[VenueName]:
        return self.venues_for_role(VenueType.signal)

    def watchlist_venues(self) -> list[VenueName]:
        return self.venues_for_role(VenueType.watchlist)

    def watchlist_only_venues(self) -> list[VenueName]:
        return [profile.venue for profile in self.profiles if self._planning_bucket_for_profile(profile) == "watchlist"]

    def execution_like_venues(self) -> list[VenueName]:
        return [
            profile.venue
            for profile in self.profiles
            if profile.default_venue_type == VenueType.execution and profile.execution_taxonomy() == "execution_like"
        ]

    def execution_blocker_codes(self, venue: VenueName) -> list[str]:
        profile = self.profile(venue)
        if profile is None:
            return []
        return profile.execution_blocker_codes()

    def required_operator_action(self, venue: VenueName) -> str:
        profile = self.profile(venue)
        if profile is None:
            return "no_order_routing"
        return profile.required_operator_action()

    def promotion_target_pathway(self, venue: VenueName) -> str | None:
        profile = self.profile(venue)
        if profile is None:
            return None
        return profile.promotion_target_pathway()

    def promotion_rules(self, venue: VenueName) -> list[str]:
        profile = self.profile(venue)
        if profile is None:
            return []
        return profile.promotion_rules()

    def pathway_ladder(self, venue: VenueName) -> list[str]:
        profile = self.profile(venue)
        if profile is None:
            return []
        return profile.pathway_ladder()

    def blocked_pathways(self, venue: VenueName) -> list[str]:
        profile = self.profile(venue)
        if profile is None:
            return []
        return profile.blocked_pathways()

    def bootstrap_qualified_venues(self) -> list[VenueName]:
        return [profile.venue for profile in self.profiles if profile.bootstrap_tier == "tier_b"]

    def bootstrap_tier_venues(self, tier: str = "tier_b") -> list[VenueName]:
        return [profile.venue for profile in self.profiles if profile.bootstrap_tier == tier]

    def bootstrap_qualification_map(self) -> dict[str, dict[str, Any]]:
        return {
            profile.venue.value: {
                "bootstrap_tier": profile.bootstrap_tier,
                "bootstrap_role": profile.bootstrap_role,
                "default_venue_type": profile.default_venue_type.value,
                "qualified_venue_types": [role.value for role in _ordered_venue_types(profile.qualified_venue_types)],
                "planning_bucket": self._planning_bucket_for_profile(profile),
                "execution_readiness": self._execution_readiness_for_profile(profile),
                "execution_equivalent": self._execution_equivalent_for_profile(profile),
                "status": self._status_for_profile(profile),
                "execution_pathway": profile.execution_pathway(),
                "pathway_modes": profile.pathway_modes(),
                "highest_actionable_mode": profile.highest_actionable_mode(),
                "readiness_stage": profile.readiness_stage(),
                "required_operator_action": profile.required_operator_action(),
                "promotion_target_pathway": profile.promotion_target_pathway(),
                "promotion_rules": profile.promotion_rules(),
                "pathway_ladder": profile.pathway_ladder(),
                "blocked_pathways": profile.blocked_pathways(),
                "promotion_rules_by_pathway": profile.promotion_rules_by_pathway(),
                "manual_execution_contract": dict(profile.manual_execution_contract()),
                "promotion_ladder": [dict(step) for step in profile.promotion_ladder()],
                "next_pathway": profile.next_pathway(),
                "next_pathway_rules": profile.next_pathway_rules(),
                "bounded_execution_equivalent": profile.bounded_execution_equivalent(),
                "bounded_execution_promotion_candidate": profile.bounded_execution_promotion_candidate(),
                "credential_gate": profile.credential_gate(),
                "api_gate": profile.api_gate(),
                "adapter_readiness": profile.adapter_readiness(),
                "execution_requirement_codes": profile.execution_requirement_codes(),
                "missing_requirement_codes": profile.missing_requirement_codes(),
                "missing_requirement_count": len(profile.missing_requirement_codes()),
                "operator_ready_now": profile.stage_summary().get("operator_ready_now", False),
                "operator_checklist": profile.operator_checklist(),
                "promotion_evidence_by_pathway": profile.promotion_evidence_by_pathway(),
                "read_only": profile.capabilities.read_only,
                "paper_capable": _feature_supported(profile.capabilities, "paper_capable"),
                "execution_capable": _feature_supported(profile.capabilities, "execution_capable"),
                "positions_capable": _feature_supported(profile.capabilities, "positions_capable"),
                "events_capable": _feature_supported(profile.capabilities, "events_capable"),
                "supports_market_feed": bool(profile.capabilities.metadata_map.get("supports_market_feed", False)),
                "supports_user_feed": bool(profile.capabilities.metadata_map.get("supports_user_feed", False)),
                "supports_rtds": bool(profile.capabilities.metadata_map.get("supports_rtds", False)),
                "planned_order_types": list(profile.planned_order_types or profile.capabilities.metadata_map.get("planned_order_types", [])),
                "supported_order_types": list(profile.supported_order_types or profile.capabilities.metadata_map.get("supported_order_types", [])),
                "execution_blocker_codes": profile.execution_blocker_codes(),
                "execution_role": self._execution_role_for_profile(profile),
                "tradeability_class": profile.tradeability_class(),
                "venue_taxonomy": profile.venue_taxonomy(),
                "execution_taxonomy": self._execution_taxonomy_for_profile(profile),
                "api_access": list(profile.capabilities.metadata_map.get("api_access", [])),
                "role_labels": profile.role_labels(),
            }
            for profile in self.profiles
        }

    def qualification_map(self) -> dict[str, list[str]]:
        return {
            profile.venue.value: profile.role_labels()
            for profile in self.profiles
        }

    def role_classification(self) -> VenueRoleClassification:
        venue_roles = self.qualification_map()
        venue_types: dict[str, str] = {}
        capability_notes: dict[str, dict[str, Any]] = {}
        role_venues: dict[str, list[str]] = {}
        role_counts: dict[str, int] = {}
        planning_bucket_map: dict[str, str] = {}
        bootstrap_tier_map: dict[str, str] = {}
        bootstrap_role_map: dict[str, str] = {}
        planned_order_types_map: dict[str, list[str]] = {}
        execution_blocker_codes_map: dict[str, list[str]] = {}
        execution_role_map: dict[str, str] = {}
        execution_taxonomy_map: dict[str, str] = {}
        execution_equivalent_venues: list[VenueName] = []
        execution_bindable_venues: list[VenueName] = []
        execution_like_venues: list[VenueName] = []
        reference_only_venues: list[VenueName] = []
        watchlist_only_venues: list[VenueName] = []
        for venue, roles in venue_roles.items():
            profile = self.profile(VenueName(venue))
            if profile is not None:
                venue_types[venue] = profile.default_venue_type.value
                bootstrap_tier_map[venue] = profile.bootstrap_tier
                bootstrap_role_map[venue] = profile.bootstrap_role
                planned_order_types_map[venue] = list(profile.planned_order_types or profile.capabilities.metadata_map.get("planned_order_types", []))
                execution_blocker_codes_map[venue] = profile.execution_blocker_codes()
                execution_role_map[venue] = self._execution_role_for_profile(profile)
                execution_taxonomy_map[venue] = profile.execution_taxonomy()
                capability_notes[venue] = {
                    **dict(profile.capabilities.metadata_map.get("capability_notes", {})),
                    **dict(profile.metadata.get("capability_notes", {})),
                }
                planning_bucket = self._planning_bucket_for_profile(profile)
                planning_bucket_map[venue] = planning_bucket
                if self._execution_equivalent_for_profile(profile):
                    execution_equivalent_venues.append(profile.venue)
                elif profile.execution_taxonomy() == "execution_bindable":
                    execution_bindable_venues.append(profile.venue)
                elif planning_bucket == "reference-only":
                    reference_only_venues.append(profile.venue)
                elif planning_bucket == "execution-equivalent":
                    execution_like_venues.append(profile.venue)
                else:
                    watchlist_only_venues.append(profile.venue)
            for role in roles:
                role_counts[role] = role_counts.get(role, 0) + 1
                role_venues.setdefault(role, [])
                if venue not in role_venues[role]:
                    role_venues[role].append(venue)
        for venues in role_venues.values():
            venues.sort()
        execution_equivalent_venues = list(dict.fromkeys(execution_equivalent_venues))
        execution_bindable_venues = list(dict.fromkeys(execution_bindable_venues))
        execution_like_venues = list(dict.fromkeys(execution_like_venues))
        reference_only_venues = list(dict.fromkeys(reference_only_venues))
        watchlist_only_venues = list(dict.fromkeys(watchlist_only_venues))
        execution_pathway_map = {
            profile.venue.value: profile.execution_pathway()
            for profile in self.profiles
        }
        execution_pathway_counts = {
            pathway: sum(1 for value in execution_pathway_map.values() if value == pathway)
            for pathway in sorted({*execution_pathway_map.values()})
        }
        readiness_stage_map = {
            profile.venue.value: profile.readiness_stage()
            for profile in self.profiles
        }
        readiness_stage_counts = {
            stage: sum(1 for value in readiness_stage_map.values() if value == stage)
            for stage in sorted({*readiness_stage_map.values()})
        }
        required_operator_action_map = {
            profile.venue.value: profile.required_operator_action()
            for profile in self.profiles
        }
        required_operator_action_counts = {
            action: sum(1 for value in required_operator_action_map.values() if value == action)
            for action in sorted({*required_operator_action_map.values()})
        }
        bounded_execution_equivalent_venues = [
            profile.venue for profile in self.profiles if profile.bounded_execution_equivalent()
        ]
        bounded_execution_promotion_candidate_venues = [
            profile.venue for profile in self.profiles if profile.bounded_execution_promotion_candidate()
        ]
        execution_role_counts = {
            role: sum(1 for value in execution_role_map.values() if value == role)
            for role in sorted({*execution_role_map.values()})
        }
        execution_taxonomy_counts = {
            taxonomy: sum(1 for value in execution_taxonomy_map.values() if value == taxonomy)
            for taxonomy in sorted({*execution_taxonomy_map.values()})
        }
        return VenueRoleClassification(
            venue_roles=venue_roles,
            venue_types=venue_types,
            role_venues=role_venues,
            role_counts={key: value for key, value in sorted(role_counts.items())},
            execution_equivalent_venues=execution_equivalent_venues,
            execution_bindable_venues=execution_bindable_venues,
            execution_like_venues=execution_like_venues,
            reference_only_venues=reference_only_venues,
            watchlist_only_venues=watchlist_only_venues,
            execution_equivalent_count=len(execution_equivalent_venues),
            execution_bindable_count=len(execution_bindable_venues),
            execution_like_count=len(execution_like_venues),
            reference_only_count=len(reference_only_venues),
            watchlist_only_count=len(watchlist_only_venues),
            execution_role=execution_role_map,
            execution_pathway=execution_pathway_map,
            execution_pathway_counts=execution_pathway_counts,
            execution_taxonomy=execution_taxonomy_map,
            execution_taxonomy_counts=execution_taxonomy_counts,
            readiness_stage=readiness_stage_map,
            readiness_stage_counts=readiness_stage_counts,
            required_operator_action=required_operator_action_map,
            required_operator_action_counts=required_operator_action_counts,
            bounded_execution_equivalent_venues=bounded_execution_equivalent_venues,
            bounded_execution_equivalent_count=len(bounded_execution_equivalent_venues),
            bounded_execution_promotion_candidate_venues=bounded_execution_promotion_candidate_venues,
            bounded_execution_promotion_candidate_count=len(bounded_execution_promotion_candidate_venues),
            execution_role_counts=execution_role_counts,
            execution_venues=self.execution_venues(),
            reference_venues=self.reference_venues(),
            signal_venues=self.signal_venues(),
            watchlist_venues=self.watchlist_venues(),
            read_only_venues=self.read_only_venues(),
            paper_capable_venues=self.paper_capable_venues(),
            execution_capable_venues=self.execution_capable_venues(),
            bootstrap_qualified_venues=self.bootstrap_qualified_venues(),
            bootstrap_tier_b_venues=self.bootstrap_tier_venues(),
            bootstrap_tier_b_count=len(self.bootstrap_tier_venues("tier_b")),
            bootstrap_roles=bootstrap_role_map,
            capability_notes=capability_notes,
            metadata={
                "venue_count": len(self.profiles),
                "execution_capable_count": len(self.execution_capable_venues()),
                "paper_capable_count": len(self.paper_capable_venues()),
                "paper_execution_like_count": len(self.paper_execution_like_venues()),
                "read_only_count": len(self.read_only_venues()),
                "execution_equivalent_count": len(execution_equivalent_venues),
                "execution_bindable_count": len(execution_bindable_venues),
                "execution_like_count": len(execution_like_venues),
                "reference_only_count": len(reference_only_venues),
                "watchlist_only_count": len(watchlist_only_venues),
                "execution_pathway": execution_pathway_map,
                "execution_pathway_counts": execution_pathway_counts,
                "readiness_stage": readiness_stage_map,
                "readiness_stage_counts": readiness_stage_counts,
                "required_operator_action": required_operator_action_map,
                "required_operator_action_counts": required_operator_action_counts,
                "bounded_execution_equivalent_venues": [venue.value for venue in bounded_execution_equivalent_venues],
                "bounded_execution_promotion_candidate_venues": [
                    venue.value for venue in bounded_execution_promotion_candidate_venues
                ],
                "credential_gate": {
                    profile.venue.value: profile.credential_gate()
                    for profile in self.profiles
                },
                "credential_gate_counts": {
                    gate: sum(1 for profile in self.profiles if profile.credential_gate() == gate)
                    for gate in sorted({profile.credential_gate() for profile in self.profiles})
                },
                "api_gate": {
                    profile.venue.value: profile.api_gate()
                    for profile in self.profiles
                },
                "api_gate_counts": {
                    gate: sum(1 for profile in self.profiles if profile.api_gate() == gate)
                    for gate in sorted({profile.api_gate() for profile in self.profiles})
                },
                "missing_requirement_count_by_venue": {
                    profile.venue.value: len(profile.missing_requirement_codes())
                    for profile in self.profiles
                },
                "operator_ready_now": {
                    profile.venue.value: bool(profile.stage_summary().get("operator_ready_now", False))
                    for profile in self.profiles
                },
                "operator_ready_count": sum(
                    1
                    for profile in self.profiles
                    if profile.stage_summary().get("operator_ready_now", False)
                ),
                "promotion_target_pathway": {
                    profile.venue.value: profile.promotion_target_pathway()
                    for profile in self.profiles
                },
                "promotion_rules": {
                    profile.venue.value: profile.promotion_rules()
                    for profile in self.profiles
                },
                "pathway_ladder": {
                    profile.venue.value: profile.pathway_ladder()
                    for profile in self.profiles
                },
                "blocked_pathways": {
                    profile.venue.value: profile.blocked_pathways()
                    for profile in self.profiles
                },
                "promotion_rules_by_pathway": {
                    profile.venue.value: profile.promotion_rules_by_pathway()
                    for profile in self.profiles
                },
                "manual_execution_contracts": {
                    profile.venue.value: dict(profile.manual_execution_contract())
                    for profile in self.profiles
                },
                "promotion_ladders": {
                    profile.venue.value: [dict(step) for step in profile.promotion_ladder()]
                    for profile in self.profiles
                },
                "execution_role_counts": execution_role_counts,
                "execution_taxonomy": {
                    profile.venue.value: profile.execution_taxonomy()
                    for profile in self.profiles
                },
                "execution_taxonomy_counts": execution_taxonomy_counts,
                "bootstrap_tier_b_count": len(self.bootstrap_tier_venues("tier_b")),
                "bootstrap_tier_map": bootstrap_tier_map,
                "bootstrap_role_map": bootstrap_role_map,
                "planned_order_types": planned_order_types_map,
                "bootstrap_role_groups": {
                    role: self.venues_for_bootstrap_role(role)
                    for role in sorted({profile.bootstrap_role for profile in self.profiles})
                },
                "planning_buckets": planning_bucket_map,
                "tradeability_map": self.tradeability_map(),
                "execution_blocker_codes": execution_blocker_codes_map,
                "execution_role": execution_role_map,
                "venue_taxonomy": {
                    profile.venue.value: profile.venue_taxonomy()
                    for profile in self.profiles
                },
                "venue_types": venue_types,
                "capability_notes": capability_notes,
                "api_access": {
                    profile.venue.value: list(profile.capabilities.metadata_map.get("api_access", []))
                    for profile in self.profiles
                },
                "supported_order_types": {
                    profile.venue.value: list(profile.capabilities.metadata_map.get("supported_order_types", []))
                    for profile in self.profiles
                },
                "planned_order_types": {
                    profile.venue.value: list(profile.planned_order_types or profile.capabilities.metadata_map.get("planned_order_types", []))
                    for profile in self.profiles
                },
            },
        )

    def role_counts(self) -> dict[str, int]:
        counts = {
            VenueType.execution.value: 0,
            VenueType.reference.value: 0,
            VenueType.signal.value: 0,
            VenueType.watchlist.value: 0,
            VenueType.experimental.value: 0,
        }
        for profile in self.profiles:
            for venue_type in {profile.default_venue_type, *profile.qualified_venue_types}:
                counts[venue_type.value] = counts.get(venue_type.value, 0) + 1
        return {key: value for key, value in counts.items() if value > 0}

    def surface_for(self, venue: VenueName) -> AdditionalVenueSurface | None:
        profile = self.profile(venue)
        if profile is None:
            return None
        planning_bucket = self._planning_bucket_for_profile(profile)
        execution_readiness = self._execution_readiness_for_profile(profile)
        execution_equivalent = self._execution_equivalent_for_profile(profile)
        status = self._status_for_profile(profile)
        execution_role = self._execution_role_for_profile(profile)
        execution_pathway = profile.execution_pathway()
        pathway_modes = profile.pathway_modes()
        highest_actionable_mode = profile.highest_actionable_mode()
        readiness_stage = profile.readiness_stage()
        required_operator_action = profile.required_operator_action()
        next_pathway = profile.next_pathway()
        next_pathway_rules = profile.next_pathway_rules()
        bounded_execution_equivalent = profile.bounded_execution_equivalent()
        bounded_execution_promotion_candidate = profile.bounded_execution_promotion_candidate()
        stage_summary = profile.stage_summary()
        runbook = {
            "runbook_id": f"{profile.venue.value}_{status}",
            "runbook_kind": "bootstrap_surface",
            "summary": (
                f"{profile.venue.value} is a {profile.bootstrap_tier} bootstrap surface; "
                f"use it as {planning_bucket} and keep it read-only."
            ),
            "recommended_action": required_operator_action,
            "status": status,
            "next_steps": [
                "Treat this venue as bootstrap-only unless explicit execution capability is proven.",
                "Keep the venue in read-only / paper / signal roles until a live adapter exists.",
                "Do not infer live order flow from the bootstrap surface.",
            ],
            "signals": {
                "backend_mode": profile.backend_mode,
                "bootstrap_tier": profile.bootstrap_tier,
                "bootstrap_role": profile.bootstrap_role,
                "planning_bucket": planning_bucket,
                "execution_readiness": execution_readiness,
                "execution_equivalent": execution_equivalent,
                "read_only": profile.capabilities.read_only,
                "execution_pathway": execution_pathway,
                "pathway_modes": list(pathway_modes),
                "highest_actionable_mode": highest_actionable_mode,
                "readiness_stage": readiness_stage,
                "execution_taxonomy": profile.execution_taxonomy(),
                "required_operator_action": required_operator_action,
                "promotion_target_pathway": profile.promotion_target_pathway(),
                "promotion_rules": profile.promotion_rules(),
                "pathway_ladder": profile.pathway_ladder(),
                "blocked_pathways": profile.blocked_pathways(),
                "promotion_rules_by_pathway": profile.promotion_rules_by_pathway(),
                "manual_execution_contract": dict(profile.manual_execution_contract()),
                "promotion_ladder": [dict(step) for step in profile.promotion_ladder()],
                "next_pathway": next_pathway,
                "next_pathway_rules": next_pathway_rules,
                "bounded_execution_equivalent": bounded_execution_equivalent,
                "bounded_execution_promotion_candidate": bounded_execution_promotion_candidate,
                "stage_summary": stage_summary,
                "paper_capable": _feature_supported(profile.capabilities, "paper_capable"),
                "execution_capable": _feature_supported(profile.capabilities, "execution_capable"),
                "positions_capable": _feature_supported(profile.capabilities, "positions_capable"),
                "events_capable": _feature_supported(profile.capabilities, "events_capable"),
                "supports_market_feed": bool(profile.capabilities.metadata_map.get("supports_market_feed", False)),
                "supports_user_feed": bool(profile.capabilities.metadata_map.get("supports_user_feed", False)),
                "supports_rtds": bool(profile.capabilities.metadata_map.get("supports_rtds", False)),
                "tradeability_class": profile.tradeability_class(),
                "venue_taxonomy": profile.venue_taxonomy(),
                "execution_role": execution_role,
                "api_access": list(profile.capabilities.metadata_map.get("api_access", [])),
                "supported_order_types": list(profile.capabilities.metadata_map.get("supported_order_types", [])),
                "planned_order_types": list(profile.planned_order_types or profile.capabilities.metadata_map.get("planned_order_types", [])),
            },
        }
        return AdditionalVenueSurface(
            venue=profile.venue,
            kind=profile.kind,
            backend_mode=profile.backend_mode,
            bootstrap_tier=profile.bootstrap_tier,
            bootstrap_role=profile.bootstrap_role,
            default_venue_type=profile.default_venue_type,
            planning_bucket=planning_bucket,
            status=status,
            execution_readiness=execution_readiness,
            execution_role=execution_role,
            execution_pathway=execution_pathway,
            execution_equivalent=execution_equivalent,
            execution_taxonomy=profile.execution_taxonomy(),
            read_only=profile.capabilities.read_only,
            paper_capable=_feature_supported(profile.capabilities, "paper_capable"),
            execution_capable=_feature_supported(profile.capabilities, "execution_capable"),
            pathway_modes=pathway_modes,
            highest_actionable_mode=highest_actionable_mode,
            readiness_stage=readiness_stage,
            required_operator_action=required_operator_action,
            promotion_target_pathway=profile.promotion_target_pathway(),
            promotion_rules=profile.promotion_rules(),
            pathway_ladder=profile.pathway_ladder(),
            blocked_pathways=profile.blocked_pathways(),
            promotion_rules_by_pathway=profile.promotion_rules_by_pathway(),
            manual_execution_contract=dict(profile.manual_execution_contract()),
            promotion_ladder=[dict(step) for step in profile.promotion_ladder()],
            next_pathway=next_pathway,
            next_pathway_rules=next_pathway_rules,
            bounded_execution_equivalent=bounded_execution_equivalent,
            bounded_execution_promotion_candidate=bounded_execution_promotion_candidate,
            stage_summary=stage_summary,
            positions_capable=_feature_supported(profile.capabilities, "positions_capable"),
            events_capable=_feature_supported(profile.capabilities, "events_capable"),
            supports_market_feed=bool(profile.capabilities.metadata_map.get("supports_market_feed", False)),
            supports_user_feed=bool(profile.capabilities.metadata_map.get("supports_user_feed", False)),
            supports_rtds=bool(profile.capabilities.metadata_map.get("supports_rtds", False)),
            planned_order_types=list(profile.planned_order_types or profile.capabilities.metadata_map.get("planned_order_types", [])),
            supported_order_types=list(profile.supported_order_types or profile.capabilities.metadata_map.get("supported_order_types", [])),
            tradeability_class=profile.tradeability_class(),
            venue_taxonomy=profile.venue_taxonomy(),
            execution_blocker_codes=profile.execution_blocker_codes(),
            metadata={
                **dict(profile.metadata),
                "planning_bucket": planning_bucket,
                "surface_status": status,
                "execution_readiness": execution_readiness,
                "execution_equivalent": execution_equivalent,
                "execution_blocker_codes": profile.execution_blocker_codes(),
                "execution_role": execution_role,
                "execution_pathway": execution_pathway,
                "pathway_modes": list(pathway_modes),
                "highest_actionable_mode": highest_actionable_mode,
                "readiness_stage": readiness_stage,
                "execution_taxonomy": profile.execution_taxonomy(),
                "required_operator_action": required_operator_action,
                "promotion_target_pathway": profile.promotion_target_pathway(),
                "promotion_rules": profile.promotion_rules(),
                "pathway_ladder": profile.pathway_ladder(),
                "blocked_pathways": profile.blocked_pathways(),
                "promotion_rules_by_pathway": profile.promotion_rules_by_pathway(),
                "manual_execution_contract": dict(profile.manual_execution_contract()),
                "promotion_ladder": [dict(step) for step in profile.promotion_ladder()],
                "next_pathway": next_pathway,
                "next_pathway_rules": next_pathway_rules,
                "bounded_execution_equivalent": bounded_execution_equivalent,
                "bounded_execution_promotion_candidate": bounded_execution_promotion_candidate,
                "stage_summary": stage_summary,
                "tradeability_class": profile.tradeability_class(),
                "venue_taxonomy": profile.venue_taxonomy(),
                "bootstrap_tier": profile.bootstrap_tier,
                "bootstrap_role": profile.bootstrap_role,
                "role_labels": profile.role_labels(),
                "api_access": list(profile.capabilities.metadata_map.get("api_access", [])),
                "supported_order_types": list(profile.supported_order_types or profile.capabilities.metadata_map.get("supported_order_types", [])),
                "planned_order_types": list(profile.planned_order_types or profile.capabilities.metadata_map.get("planned_order_types", [])),
            },
            role_labels=profile.role_labels(),
            capability_notes={
                **dict(profile.capabilities.metadata_map.get("capability_notes", {})),
                **dict(profile.metadata.get("capability_notes", {})),
            },
            runbook=runbook,
        )

    def execution_readiness_map(self) -> dict[str, dict[str, Any]]:
        return {
            profile.venue.value: {
                "bootstrap_tier": profile.bootstrap_tier,
                "bootstrap_role": profile.bootstrap_role,
                "default_venue_type": profile.default_venue_type.value,
                "planning_bucket": self._planning_bucket_for_profile(profile),
                "execution_readiness": self._execution_readiness_for_profile(profile),
                "execution_blocker_codes": profile.execution_blocker_codes(),
                "read_only": profile.capabilities.read_only,
                "execution_pathway": profile.execution_pathway(),
                "pathway_modes": profile.pathway_modes(),
                "highest_actionable_mode": profile.highest_actionable_mode(),
                "readiness_stage": profile.readiness_stage(),
                "required_operator_action": profile.required_operator_action(),
                "promotion_target_pathway": profile.promotion_target_pathway(),
                "promotion_rules": profile.promotion_rules(),
                "pathway_ladder": profile.pathway_ladder(),
                "blocked_pathways": profile.blocked_pathways(),
                "promotion_rules_by_pathway": profile.promotion_rules_by_pathway(),
                "next_pathway": profile.next_pathway(),
                "next_pathway_rules": profile.next_pathway_rules(),
                "bounded_execution_equivalent": profile.bounded_execution_equivalent(),
                "bounded_execution_promotion_candidate": profile.bounded_execution_promotion_candidate(),
                "credential_gate": profile.credential_gate(),
                "api_gate": profile.api_gate(),
                "adapter_readiness": profile.adapter_readiness(),
                "execution_requirement_codes": profile.execution_requirement_codes(),
                "missing_requirement_codes": profile.missing_requirement_codes(),
                "missing_requirement_count": len(profile.missing_requirement_codes()),
                "operator_ready_now": profile.stage_summary().get("operator_ready_now", False),
                "operator_checklist": profile.operator_checklist(),
                "promotion_evidence_by_pathway": profile.promotion_evidence_by_pathway(),
                "paper_capable": _feature_supported(profile.capabilities, "paper_capable"),
                "execution_capable": _feature_supported(profile.capabilities, "execution_capable"),
                "positions_capable": _feature_supported(profile.capabilities, "positions_capable"),
                "events_capable": _feature_supported(profile.capabilities, "events_capable"),
                "supports_market_feed": bool(profile.capabilities.metadata_map.get("supports_market_feed", False)),
                "supports_user_feed": bool(profile.capabilities.metadata_map.get("supports_user_feed", False)),
                "supports_rtds": bool(profile.capabilities.metadata_map.get("supports_rtds", False)),
                "tradeability_class": profile.tradeability_class(),
                "venue_taxonomy": profile.venue_taxonomy(),
                "execution_role": self._execution_role_for_profile(profile),
                "api_access": list(profile.capabilities.metadata_map.get("api_access", [])),
                "supported_order_types": list(profile.capabilities.metadata_map.get("supported_order_types", [])),
                "role_labels": profile.role_labels(),
            }
            for profile in self.profiles
        }

    def surface_map(self) -> dict[str, AdditionalVenueSurface]:
        surfaces: dict[str, AdditionalVenueSurface] = {}
        for profile in self.profiles:
            surface = self.surface_for(profile.venue)
            if surface is not None:
                surfaces[profile.venue.value] = surface
        return surfaces

    @staticmethod
    def _planning_bucket_for_profile(profile: AdditionalVenueProfile) -> str:
        if profile.default_venue_type == VenueType.execution or VenueType.execution in profile.qualified_venue_types:
            return "execution-equivalent"
        if profile.default_venue_type == VenueType.reference or VenueType.reference in profile.qualified_venue_types:
            return "reference-only"
        return "watchlist"

    @staticmethod
    def _execution_readiness_for_profile(profile: AdditionalVenueProfile) -> str:
        if profile.capabilities.execution and profile.backend_mode != "bootstrap":
            return "live_execution"
        if profile.kind == AdditionalVenueKind.execution_like:
            if profile.execution_bindable_supported():
                return "bootstrap_execution_bindable"
            return "bootstrap_execution_like_read_only" if profile.capabilities.read_only else "bootstrap_execution_like"
        if profile.kind == AdditionalVenueKind.reference:
            return "bootstrap_reference_read_only" if profile.capabilities.read_only else "bootstrap_reference"
        if profile.kind == AdditionalVenueKind.signal:
            return "bootstrap_signal_read_only" if profile.capabilities.read_only else "bootstrap_signal"
        if profile.kind == AdditionalVenueKind.watchlist:
            return "bootstrap_watchlist_read_only" if profile.capabilities.read_only else "bootstrap_watchlist"
        return "bootstrap_read_only"

    @staticmethod
    def _execution_equivalent_for_profile(profile: AdditionalVenueProfile) -> bool:
        if profile.backend_mode == "bootstrap":
            return False
        return bool(_feature_supported(profile.capabilities, "execution_capable"))

    @staticmethod
    def _status_for_profile(profile: AdditionalVenueProfile) -> str:
        planning_bucket = VenueCapabilityMatrix._planning_bucket_for_profile(profile)
        if profile.backend_mode == "bootstrap" and profile.capabilities.read_only:
            if planning_bucket == "execution-equivalent":
                return "bootstrap_execution_bindable" if profile.execution_bindable_supported() else "bootstrap_execution_like_read_only"
            if planning_bucket == "reference-only":
                return "bootstrap_reference_read_only"
            if planning_bucket == "watchlist":
                return "bootstrap_watchlist_read_only"
            return "bootstrap_read_only"
        if profile.capabilities.execution:
            return "execution_ready"
        if profile.execution_bindable_supported():
            return "execution_bindable"
        if profile.capabilities.positions or profile.capabilities.trades:
            return "paper_ready"
        return "watchlist"

    @staticmethod
    def _execution_role_for_profile(profile: AdditionalVenueProfile) -> str:
        if profile.backend_mode != "bootstrap" and profile.capabilities.execution:
            return "execution_equivalent"
        if profile.execution_bindable_supported():
            return "execution_bindable"
        if profile.kind == AdditionalVenueKind.execution_like:
            return "execution_like"
        if profile.kind == AdditionalVenueKind.reference:
            return "reference_only"
        if profile.kind == AdditionalVenueKind.signal:
            return "signal_only"
        return "watchlist_only"

    @staticmethod
    def _execution_taxonomy_for_profile(profile: AdditionalVenueProfile) -> str:
        if profile.backend_mode != "bootstrap" and profile.live_execution_supported():
            return "execution_ready"
        if profile.backend_mode != "bootstrap" and profile.bounded_execution_supported():
            return "execution_equivalent"
        if profile.execution_bindable_supported():
            return "execution_bindable"
        return "execution_like"


def _ordered_venue_types(values: set[VenueType]) -> list[VenueType]:
    rank = {
        VenueType.reference: 0,
        VenueType.execution: 1,
        VenueType.signal: 2,
        VenueType.watchlist: 3,
        VenueType.experimental: 4,
    }
    return sorted(values, key=lambda item: (rank.get(item, 99), item.value))


def _feature_supported(capabilities: VenueCapabilitiesModel, feature: str) -> bool:
    value = getattr(capabilities, feature, None)
    if isinstance(value, bool):
        return value
    return bool(capabilities.metadata_map.get(feature, False))


def _bootstrap_capability_metadata(
    *,
    backend_mode: str,
    venue_kind: str,
    venue_type: str,
    role_labels: list[str],
    api_access: list[str] | None = None,
    supported_order_types: list[str] | None = None,
    read_only: bool,
    paper_capable: bool,
    execution_capable: bool,
    positions_capable: bool,
    events_capable: bool,
    discovery_note: str,
    orderbook_note: str,
    trades_note: str,
    execution_note: str,
    websocket_note: str,
    paper_note: str,
    automation_constraints: list[str],
    rate_limit_notes: list[str],
    venue_taxonomy: str | None = None,
    tradeability_class: str | None = None,
    execution_taxonomy: str | None = None,
) -> dict[str, Any]:
    return _capability_metadata(
        backend_mode=backend_mode,
        venue_kind=venue_kind,
        venue_type=venue_type,
        role_labels=role_labels,
        api_access=list(api_access or []),
        supported_order_types=list(supported_order_types or []),
        read_only=read_only,
        paper_capable=paper_capable,
        execution_capable=execution_capable,
        positions_capable=positions_capable,
        events_capable=events_capable,
        discovery_notes=[discovery_note],
        orderbook_notes=[orderbook_note],
        trades_notes=[trades_note],
        execution_notes=[execution_note],
        websocket_notes=[websocket_note],
        paper_mode_notes=[paper_note],
        automation_constraints=automation_constraints,
        rate_limit_notes=rate_limit_notes,
        compliance_notes=["Bootstrap venue profiles are read-only and do not place live orders."],
        venue_taxonomy=venue_taxonomy,
        tradeability_class=tradeability_class,
        execution_taxonomy=execution_taxonomy,
    )


def _bootstrap_market(
    *,
    venue: VenueName,
    market_id: str,
    title: str,
    question: str,
    slug: str,
    resolution_source: str,
    source_url: str | None,
    venue_type: VenueType,
    canonical_event_id: str,
    liquidity: float,
    volume: float,
    tags: list[str],
    categories: list[str],
    probability: float,
    description: str,
) -> MarketDescriptor:
    return MarketDescriptor(
        market_id=market_id,
        venue=venue,
        venue_type=venue_type,
        title=title,
        question=question,
        slug=slug,
        status=MarketStatus.open,
        source_url=source_url,
        canonical_event_id=canonical_event_id,
        resolution_source=resolution_source,
        resolution_date=datetime.now(timezone.utc),
        close_time=datetime.now(timezone.utc),
        volume=volume,
        liquidity=liquidity,
        tags=tags,
        categories=categories,
        description=description,
        active=True,
        closed=False,
        outcomes=["Yes", "No"],
        token_ids=[f"{market_id}:yes", f"{market_id}:no"],
        metadata={
            "bootstrap": True,
            "bootstrap_probability": probability,
            "venue_kind": venue_type.value,
        },
        raw={
            "bootstrap": True,
            "source_url": source_url,
        },
    )


def _build_snapshot(descriptor: MarketDescriptor) -> MarketSnapshot:
    probability = float(descriptor.metadata.get("bootstrap_probability", 0.5))
    probability = max(0.0, min(1.0, probability))
    spread_bps = max(40.0, round(120.0 - min(60.0, descriptor.clarity_score * 80.0), 2))
    bid = max(0.01, round(probability - spread_bps / 20000.0, 6))
    ask = min(0.99, round(probability + spread_bps / 20000.0, 6))
    return MarketSnapshot(
        market_id=descriptor.market_id,
        venue=descriptor.venue,
        venue_type=descriptor.venue_type,
        title=descriptor.title,
        question=descriptor.question,
        status=descriptor.status,
        source_url=descriptor.source_url,
        resolution_source=descriptor.resolution_source,
        canonical_event_id=descriptor.canonical_event_id,
        liquidity=descriptor.liquidity,
        volume=descriptor.volume,
        orderbook=MarketOrderBook(
            bids=[OrderBookLevel(price=bid, size=max(1.0, (descriptor.liquidity or 1000.0) / 5000.0))],
            asks=[OrderBookLevel(price=ask, size=max(1.0, (descriptor.liquidity or 1000.0) / 5000.0))],
            source="bootstrap",
        ),
        market_implied_probability=probability,
        fair_probability_hint=probability,
        spread_bps=spread_bps,
        staleness_ms=0,
        price_yes=probability,
        price_no=round(1.0 - probability, 6),
        midpoint_yes=probability,
        orderbook_depth=descriptor.liquidity,
        tags=list(descriptor.tags),
        metadata={
            "bootstrap": True,
            "venue_kind": descriptor.venue_type.value,
        },
        raw={"bootstrap": True},
    )


def _build_policy(descriptor: MarketDescriptor) -> ResolutionPolicy:
    return ResolutionPolicy(
        market_id=descriptor.market_id,
        venue=descriptor.venue,
        official_source=descriptor.resolution_source or descriptor.source_url or f"{descriptor.venue.value}-bootstrap",
        source_url=descriptor.source_url,
        resolution_rules=["bootstrap_descriptor", "official_source_present"],
        ambiguity_flags=[],
        manual_review_required=False,
        status=ResolutionStatus.clear,
        metadata={"bootstrap": True, "source_url": descriptor.source_url},
    )


def _build_evidence(descriptor: MarketDescriptor) -> list[EvidencePacket]:
    notes = [
        f"Bootstrap descriptor for {descriptor.venue.value}:{descriptor.market_id}",
        f"Bootstrap clarity score {descriptor.clarity_score:.3f}",
    ]
    return [
        EvidencePacket(
            market_id=descriptor.market_id,
            venue=descriptor.venue,
            source_kind=SourceKind.model,
            claim=note,
            stance="neutral",
            summary=note,
            source_url=descriptor.source_url,
            raw_text=descriptor.question,
            confidence=0.55,
            freshness_score=0.95,
            credibility_score=0.75,
            tags=["bootstrap", descriptor.venue.value],
            metadata={"bootstrap": True},
        )
        for note in notes
    ]


def _build_trades(descriptor: MarketDescriptor) -> list[TradeRecord]:
    snapshot = _build_snapshot(descriptor)
    probability = snapshot.market_implied_probability or 0.5
    return [
        TradeRecord(
            price=round(max(0.01, min(0.99, probability - 0.02)), 6),
            size=max(1.0, (descriptor.liquidity or 1000.0) / 10000.0),
            side=TradeSide.buy,
            metadata={"bootstrap": True, "venue": descriptor.venue.value},
        ),
        TradeRecord(
            price=round(max(0.01, min(0.99, probability + 0.02)), 6),
            size=max(1.0, (descriptor.liquidity or 1000.0) / 12000.0),
            side=TradeSide.sell,
            metadata={"bootstrap": True, "venue": descriptor.venue.value},
        ),
    ]


MANIFOLD_PROFILE = AdditionalVenueProfile(
    venue=VenueName.manifold,
    kind=AdditionalVenueKind.signal,
    backend_mode="bootstrap",
    bootstrap_role="signal_bootstrap",
    default_venue_type=VenueType.signal,
    qualified_venue_types={VenueType.signal, VenueType.watchlist},
    source_url="https://manifold.markets",
    planned_order_types=[],
    capabilities=VenueCapabilitiesModel(
        venue=VenueName.manifold,
        discovery=True,
        metadata=True,
        orderbook=False,
        trades=True,
        positions=True,
        execution=False,
        streaming=False,
        interviews=False,
        read_only=True,
        supports_replay=True,
        metadata_map=_bootstrap_capability_metadata(
            backend_mode="bootstrap",
            venue_kind="signal",
            venue_type="signal",
            venue_taxonomy="social_signal",
            tradeability_class="signal_paper_only",
            role_labels=["signal", "watchlist"],
            api_access=["catalog", "snapshot", "trades", "positions", "events", "evidence"],
            supported_order_types=[],
            read_only=True,
            paper_capable=True,
            execution_capable=False,
            positions_capable=True,
            events_capable=True,
            discovery_note="Bootstrap discovery is available through synthetic signal descriptors.",
            orderbook_note="No live orderbook; signal markets are represented as bootstrap snapshots.",
            trades_note="Synthetic trade records are surfaced for research and replay.",
            execution_note="No live execution is permitted for signal bootstrap venues.",
            websocket_note="No live websocket stream is exposed in bootstrap mode.",
            paper_note="Paper planning is supported from bootstrap signal data.",
            automation_constraints=["Read-only bootstrap profile.", "No live order placement."],
            rate_limit_notes=["Bootstrap mode does not consume live venue rate limits."],
            execution_taxonomy="execution_like",
        ),
    ),
    metadata={
        "venue_type": "signal",
        "venue_taxonomy": "social_signal",
        "tradeability_class": "signal_paper_only",
        "role_labels": ["signal", "watchlist"],
        "api_access": ["catalog", "snapshot", "trades", "positions", "events", "evidence"],
        "supported_order_types": [],
        "planned_order_types": [],
        "capability_notes": {
            "discovery": "Synthetic signal discovery only.",
            "execution": "Read-only, no live execution.",
        },
    },
    descriptors=[
        _bootstrap_market(
            venue=VenueName.manifold,
            market_id="manifold-ai-adoption-2026",
            title="Will AI adoption exceed expectations in 2026?",
            question="Will AI adoption exceed expectations in 2026?",
            slug="ai-adoption-2026",
            resolution_source="https://manifold.markets",
            source_url="https://manifold.markets/m/ai-adoption-2026",
            venue_type=VenueType.signal,
            canonical_event_id="manifold_ai_adoption_2026",
            liquidity=12_000.0,
            volume=35_000.0,
            tags=["ai", "technology"],
            categories=["tech"],
            probability=0.58,
            description="Bootstrap Manifold signal market",
        ),
        _bootstrap_market(
            venue=VenueName.manifold,
            market_id="manifold-fed-inflation-2026",
            title="Will inflation undershoot forecasts in 2026?",
            question="Will inflation undershoot forecasts in 2026?",
            slug="fed-inflation-2026",
            resolution_source="https://manifold.markets",
            source_url="https://manifold.markets/m/fed-inflation-2026",
            venue_type=VenueType.signal,
            canonical_event_id="manifold_inflation_2026",
            liquidity=10_000.0,
            volume=28_000.0,
            tags=["macro", "inflation"],
            categories=["economy"],
            probability=0.44,
            description="Bootstrap macro signal market",
        ),
    ],
    notes=["signal-first venue", "bootstrap read-only descriptors"],
)


METACULUS_PROFILE = AdditionalVenueProfile(
    venue=VenueName.metaculus,
    kind=AdditionalVenueKind.reference,
    backend_mode="bootstrap",
    bootstrap_role="reference_bootstrap",
    default_venue_type=VenueType.reference,
    qualified_venue_types={VenueType.reference, VenueType.watchlist},
    source_url="https://www.metaculus.com",
    planned_order_types=[],
    capabilities=VenueCapabilitiesModel(
        venue=VenueName.metaculus,
        discovery=True,
        metadata=True,
        orderbook=False,
        trades=False,
        positions=True,
        execution=False,
        streaming=False,
        interviews=True,
        read_only=True,
        supports_replay=True,
        metadata_map=_bootstrap_capability_metadata(
            backend_mode="bootstrap",
            venue_kind="reference",
            venue_type="reference",
            venue_taxonomy="forecast_reference",
            tradeability_class="reference_paper_only",
            role_labels=["reference", "watchlist"],
            api_access=["catalog", "snapshot", "positions", "events", "evidence"],
            supported_order_types=[],
            read_only=True,
            paper_capable=True,
            execution_capable=False,
            positions_capable=True,
            events_capable=True,
            discovery_note="Reference discovery is available through the bootstrap question catalog.",
            orderbook_note="No orderbook is exposed for reference-only bootstrap venues.",
            trades_note="No live trades are exposed for reference-only bootstrap venues.",
            execution_note="No execution routing is permitted for reference-only venues.",
            websocket_note="No live websocket stream is exposed for reference-only venues.",
            paper_note="Paper planning is supported for research and comparison.",
            automation_constraints=["Read-only reference profile.", "No live execution."],
            rate_limit_notes=["Bootstrap mode does not consume live venue rate limits."],
            execution_taxonomy="execution_like",
        ),
    ),
    metadata={
        "venue_type": "reference",
        "venue_taxonomy": "forecast_reference",
        "tradeability_class": "reference_paper_only",
        "role_labels": ["reference", "watchlist"],
        "api_access": ["catalog", "snapshot", "positions", "events", "evidence"],
        "supported_order_types": [],
        "planned_order_types": [],
        "capability_notes": {
            "discovery": "Reference discovery is available for research.",
            "execution": "Reference-only, no execution.",
        },
    },
    descriptors=[
        _bootstrap_market(
            venue=VenueName.metaculus,
            market_id="metaculus-btc-120k-2026",
            title="Will BTC trade above 120k by year end 2026?",
            question="Will BTC trade above 120k by year end 2026?",
            slug="btc-120k-2026",
            resolution_source="https://www.metaculus.com",
            source_url="https://www.metaculus.com/questions/btc-120k-2026/",
            venue_type=VenueType.reference,
            canonical_event_id="metaculus_btc_120k_2026",
            liquidity=2_500.0,
            volume=5_000.0,
            tags=["crypto", "btc"],
            categories=["crypto"],
            probability=0.61,
            description="Bootstrap reference market",
        ),
        _bootstrap_market(
            venue=VenueName.metaculus,
            market_id="metaculus-us-election-2028",
            title="Will the 2028 US election be decided within 24 hours?",
            question="Will the 2028 US election be decided within 24 hours?",
            slug="us-election-2028",
            resolution_source="https://www.metaculus.com",
            source_url="https://www.metaculus.com/questions/us-election-2028/",
            venue_type=VenueType.reference,
            canonical_event_id="metaculus_us_election_2028",
            liquidity=2_000.0,
            volume=4_800.0,
            tags=["politics", "election"],
            categories=["politics"],
            probability=0.47,
            description="Bootstrap reference market",
        ),
    ],
    notes=["reference-first venue", "interview-capable bootstrap"],
)


ROBINHOOD_PROFILE = AdditionalVenueProfile(
    venue=VenueName.robinhood,
    kind=AdditionalVenueKind.execution_like,
    backend_mode="bootstrap",
    bootstrap_role="event_contract_bootstrap",
    default_venue_type=VenueType.execution,
    qualified_venue_types={VenueType.execution, VenueType.watchlist},
    source_url="https://robinhood.com",
    planned_order_types=["limit"],
    capabilities=VenueCapabilitiesModel(
        venue=VenueName.robinhood,
        discovery=True,
        metadata=True,
        orderbook=True,
        trades=True,
        positions=True,
        execution=False,
        streaming=False,
        interviews=False,
        read_only=True,
        supports_replay=True,
        metadata_map={
            **_bootstrap_capability_metadata(
            backend_mode="bootstrap",
            venue_kind="execution_like",
            venue_type="execution",
            venue_taxonomy="centralized_execution_like",
            tradeability_class="execution_bindable_dry_run",
            role_labels=["execution", "watchlist"],
            api_access=["catalog", "snapshot", "orderbook", "trades", "positions", "events", "evidence"],
            supported_order_types=[],
            read_only=True,
            paper_capable=True,
                execution_capable=False,
                positions_capable=True,
                events_capable=True,
                discovery_note="Execution-like discovery is available from the bootstrap catalog.",
                orderbook_note="Synthetic orderbook snapshots are available for planning only.",
                trades_note="Synthetic trade records are available for paper review.",
                execution_note="No live order placement is allowed in bootstrap mode.",
                websocket_note="No live websocket is exposed; snapshots and polling only.",
                paper_note="Paper mode is supported via execution-like bootstrap descriptors.",
                automation_constraints=["Read-only bootstrap profile.", "No live automation."],
                rate_limit_notes=["Bootstrap mode does not consume live venue rate limits."],
                execution_taxonomy="execution_bindable",
            ),
            "planned_order_types": ["limit"],
            "automation_mode": "mockable_execution_like",
        },
    ),
    metadata={
        "venue_type": "execution",
        "venue_taxonomy": "centralized_execution_like",
        "tradeability_class": "execution_bindable_dry_run",
        "execution_taxonomy": "execution_bindable",
        "role_labels": ["execution", "watchlist"],
        "api_access": ["catalog", "snapshot", "orderbook", "trades", "positions", "events", "evidence"],
        "supported_order_types": [],
        "planned_order_types": ["limit"],
        "capability_notes": {
            "discovery": "Execution-like discovery with bindable dry-run surfaces.",
            "execution": "Read-only bootstrap profile; dry-run binding is available but live execution is not.",
        },
    },
    descriptors=[
        _bootstrap_market(
            venue=VenueName.robinhood,
            market_id="robinhood-earnings-volatility-q4-2026",
            title="Will earnings volatility stay elevated into Q4 2026?",
            question="Will earnings volatility stay elevated into Q4 2026?",
            slug="earnings-volatility-q4-2026",
            resolution_source="https://robinhood.com",
            source_url="https://robinhood.com/markets/earnings-volatility-q4-2026",
            venue_type=VenueType.execution,
            canonical_event_id="robinhood_earnings_volatility_q4_2026",
            liquidity=20_000.0,
            volume=42_000.0,
            tags=["markets", "volatility"],
            categories=["finance"],
            probability=0.52,
            description="Bootstrap execution-like market",
        ),
        _bootstrap_market(
            venue=VenueName.robinhood,
            market_id="robinhood-bitcoin-2026",
            title="Will Bitcoin close 2026 above 100k?",
            question="Will Bitcoin close 2026 above 100k?",
            slug="bitcoin-2026",
            resolution_source="https://robinhood.com",
            source_url="https://robinhood.com/markets/bitcoin-2026",
            venue_type=VenueType.execution,
            canonical_event_id="robinhood_bitcoin_2026",
            liquidity=18_000.0,
            volume=39_000.0,
            tags=["crypto", "btc"],
            categories=["crypto"],
            probability=0.49,
            description="Bootstrap execution-like market",
        ),
    ],
    notes=["execution-bindable bootstrap", "dry-run ready descriptors"],
)


CRYPTOCOM_PROFILE = AdditionalVenueProfile(
    venue=VenueName.cryptocom,
    kind=AdditionalVenueKind.execution_like,
    backend_mode="bootstrap",
    bootstrap_role="event_contract_bootstrap",
    default_venue_type=VenueType.execution,
    qualified_venue_types={VenueType.execution, VenueType.watchlist},
    source_url="https://crypto.com",
    planned_order_types=["limit"],
    capabilities=VenueCapabilitiesModel(
        venue=VenueName.cryptocom,
        discovery=True,
        metadata=True,
        orderbook=True,
        trades=True,
        positions=True,
        execution=False,
        streaming=False,
        interviews=False,
        read_only=True,
        supports_replay=True,
        metadata_map={
            **_bootstrap_capability_metadata(
            backend_mode="bootstrap",
            venue_kind="execution_like",
            venue_type="execution",
            venue_taxonomy="centralized_execution_like",
            tradeability_class="execution_bindable_dry_run",
            role_labels=["execution", "watchlist"],
            api_access=["catalog", "snapshot", "orderbook", "trades", "positions", "events", "evidence"],
            supported_order_types=[],
            read_only=True,
            paper_capable=True,
                execution_capable=False,
                positions_capable=True,
                events_capable=True,
                discovery_note="Execution-like discovery is available from the bootstrap catalog.",
                orderbook_note="Synthetic orderbook snapshots are available for planning only.",
                trades_note="Synthetic trade records are available for paper review.",
                execution_note="No live order placement is allowed in bootstrap mode.",
                websocket_note="No live websocket is exposed; snapshots and polling only.",
                paper_note="Paper mode is supported via execution-like bootstrap descriptors.",
                automation_constraints=["Read-only bootstrap profile.", "No live automation."],
                rate_limit_notes=["Bootstrap mode does not consume live venue rate limits."],
                execution_taxonomy="execution_bindable",
            ),
            "planned_order_types": ["limit"],
            "automation_mode": "mockable_execution_like",
        },
    ),
    metadata={
        "venue_type": "execution",
        "venue_taxonomy": "centralized_execution_like",
        "tradeability_class": "execution_bindable_dry_run",
        "execution_taxonomy": "execution_bindable",
        "role_labels": ["execution", "watchlist"],
        "api_access": ["catalog", "snapshot", "orderbook", "trades", "positions", "events", "evidence"],
        "supported_order_types": [],
        "planned_order_types": ["limit"],
        "capability_notes": {
            "discovery": "Execution-like discovery with bindable dry-run surfaces.",
            "execution": "Read-only bootstrap profile; dry-run binding is available but live execution is not.",
        },
    },
    descriptors=[
        _bootstrap_market(
            venue=VenueName.cryptocom,
            market_id="cryptocom-btc-2026",
            title="Will BTC outperform ETH in 2026?",
            question="Will BTC outperform ETH in 2026?",
            slug="btc-outperform-eth-2026",
            resolution_source="https://crypto.com",
            source_url="https://crypto.com/markets/btc-outperform-eth-2026",
            venue_type=VenueType.execution,
            canonical_event_id="cryptocom_btc_outperform_eth_2026",
            liquidity=16_000.0,
            volume=31_000.0,
            tags=["crypto"],
            categories=["crypto"],
            probability=0.54,
            description="Bootstrap execution-like market",
        ),
        _bootstrap_market(
            venue=VenueName.cryptocom,
            market_id="cryptocom-eth-2026",
            title="Will ETH upgrade timelines hold in 2026?",
            question="Will ETH upgrade timelines hold in 2026?",
            slug="eth-upgrades-2026",
            resolution_source="https://crypto.com",
            source_url="https://crypto.com/markets/eth-upgrades-2026",
            venue_type=VenueType.execution,
            canonical_event_id="cryptocom_eth_upgrades_2026",
            liquidity=14_000.0,
            volume=29_000.0,
            tags=["crypto", "eth"],
            categories=["crypto"],
            probability=0.46,
            description="Bootstrap execution-like market",
        ),
    ],
    notes=["execution-bindable bootstrap", "synthetic orderbook/trades"],
)


OMEN_PROFILE = AdditionalVenueProfile(
    venue=VenueName.omen,
    kind=AdditionalVenueKind.execution_like,
    backend_mode="bootstrap",
    bootstrap_role="decentralized_execution_bootstrap",
    default_venue_type=VenueType.execution,
    qualified_venue_types={VenueType.execution, VenueType.watchlist},
    source_url="https://omen.eth.limo",
    planned_order_types=["limit"],
    capabilities=VenueCapabilitiesModel(
        venue=VenueName.omen,
        discovery=True,
        metadata=True,
        orderbook=True,
        trades=True,
        positions=True,
        execution=False,
        streaming=False,
        interviews=False,
        read_only=True,
        supports_replay=True,
        metadata_map={
            **_bootstrap_capability_metadata(
            backend_mode="bootstrap",
            venue_kind="execution_like",
            venue_type="execution",
            venue_taxonomy="decentralized_execution_like",
            tradeability_class="execution_bindable_dry_run",
            role_labels=["execution", "watchlist"],
            api_access=["catalog", "snapshot", "orderbook", "trades", "positions", "events", "evidence"],
            supported_order_types=[],
            read_only=True,
            paper_capable=True,
                execution_capable=False,
                positions_capable=True,
                events_capable=True,
                discovery_note="Decentralized execution-like discovery is available from the bootstrap catalog.",
                orderbook_note="Synthetic orderbook snapshots are exposed for decentralized routing rehearsal only.",
                trades_note="Synthetic trade records are exposed for paper and replay workflows.",
                execution_note="No live on-chain order placement is permitted in bootstrap mode.",
                websocket_note="No live websocket is exposed; bootstrap snapshots are polling-friendly only.",
                paper_note="Paper rehearsal is supported via decentralized execution-like bootstrap descriptors.",
                automation_constraints=["Read-only bootstrap profile.", "No live on-chain automation."],
                rate_limit_notes=["Bootstrap mode does not consume live venue rate limits."],
                execution_taxonomy="execution_bindable",
            ),
            "planned_order_types": ["limit"],
            "automation_mode": "mockable_execution_like",
        },
    ),
    metadata={
        "venue_type": "execution",
        "venue_taxonomy": "decentralized_execution_like",
        "tradeability_class": "execution_bindable_dry_run",
        "execution_taxonomy": "execution_bindable",
        "role_labels": ["execution", "watchlist"],
        "api_access": ["catalog", "snapshot", "orderbook", "trades", "positions", "events", "evidence"],
        "supported_order_types": [],
        "planned_order_types": ["limit"],
        "capability_notes": {
            "discovery": "Decentralized execution-like discovery with bindable dry-run surfaces.",
            "execution": "Read-only bootstrap profile; dry-run binding is available but live on-chain execution is not.",
        },
    },
    descriptors=[
        _bootstrap_market(
            venue=VenueName.omen,
            market_id="omen-stablecoin-dominance-2026",
            title="Will stablecoin dominance increase in 2026?",
            question="Will stablecoin dominance increase in 2026?",
            slug="stablecoin-dominance-2026",
            resolution_source="https://omen.eth.limo",
            source_url="https://omen.eth.limo/markets/stablecoin-dominance-2026",
            venue_type=VenueType.execution,
            canonical_event_id="omen_stablecoin_dominance_2026",
            liquidity=15_500.0,
            volume=30_000.0,
            tags=["crypto", "stablecoins"],
            categories=["crypto"],
            probability=0.57,
            description="Bootstrap decentralized execution-like market",
        ),
        _bootstrap_market(
            venue=VenueName.omen,
            market_id="omen-eth-etf-2026",
            title="Will ETH ETF flows stay positive in 2026?",
            question="Will ETH ETF flows stay positive in 2026?",
            slug="eth-etf-flows-2026",
            resolution_source="https://omen.eth.limo",
            source_url="https://omen.eth.limo/markets/eth-etf-flows-2026",
            venue_type=VenueType.execution,
            canonical_event_id="omen_eth_etf_flows_2026",
            liquidity=13_500.0,
            volume=27_000.0,
            tags=["crypto", "eth"],
            categories=["crypto"],
            probability=0.48,
            description="Bootstrap decentralized execution-like market",
        ),
    ],
    notes=["execution-bindable bootstrap", "decentralized synthetic descriptors"],
)


AUGUR_PROFILE = AdditionalVenueProfile(
    venue=VenueName.augur,
    kind=AdditionalVenueKind.execution_like,
    backend_mode="bootstrap",
    bootstrap_role="decentralized_execution_bootstrap",
    default_venue_type=VenueType.execution,
    qualified_venue_types={VenueType.execution, VenueType.watchlist},
    source_url="https://augur.net",
    planned_order_types=["limit"],
    capabilities=VenueCapabilitiesModel(
        venue=VenueName.augur,
        discovery=True,
        metadata=True,
        orderbook=True,
        trades=True,
        positions=True,
        execution=False,
        streaming=False,
        interviews=False,
        read_only=True,
        supports_replay=True,
        metadata_map={
            **_bootstrap_capability_metadata(
            backend_mode="bootstrap",
            venue_kind="execution_like",
            venue_type="execution",
            venue_taxonomy="decentralized_execution_like",
            tradeability_class="execution_bindable_dry_run",
            role_labels=["execution", "watchlist"],
            api_access=["catalog", "snapshot", "orderbook", "trades", "positions", "events", "evidence"],
            supported_order_types=[],
            read_only=True,
            paper_capable=True,
                execution_capable=False,
                positions_capable=True,
                events_capable=True,
                discovery_note="Decentralized execution-like discovery is available from the bootstrap catalog.",
                orderbook_note="Synthetic orderbook snapshots are exposed for decentralized routing rehearsal only.",
                trades_note="Synthetic trade records are exposed for paper and replay workflows.",
                execution_note="No live on-chain order placement is permitted in bootstrap mode.",
                websocket_note="No live websocket is exposed; bootstrap snapshots are polling-friendly only.",
                paper_note="Paper rehearsal is supported via decentralized execution-like bootstrap descriptors.",
                automation_constraints=["Read-only bootstrap profile.", "No live on-chain automation."],
                rate_limit_notes=["Bootstrap mode does not consume live venue rate limits."],
                execution_taxonomy="execution_bindable",
            ),
            "planned_order_types": ["limit"],
            "automation_mode": "mockable_execution_like",
        },
    ),
    metadata={
        "venue_type": "execution",
        "venue_taxonomy": "decentralized_execution_like",
        "tradeability_class": "execution_bindable_dry_run",
        "execution_taxonomy": "execution_bindable",
        "role_labels": ["execution", "watchlist"],
        "api_access": ["catalog", "snapshot", "orderbook", "trades", "positions", "events", "evidence"],
        "supported_order_types": [],
        "planned_order_types": ["limit"],
        "capability_notes": {
            "discovery": "Decentralized execution-like discovery with bindable dry-run surfaces.",
            "execution": "Read-only bootstrap profile; dry-run binding is available but live on-chain execution is not.",
        },
    },
    descriptors=[
        _bootstrap_market(
            venue=VenueName.augur,
            market_id="augur-fed-balance-sheet-2026",
            title="Will the Fed balance sheet expand again in 2026?",
            question="Will the Fed balance sheet expand again in 2026?",
            slug="fed-balance-sheet-2026",
            resolution_source="https://augur.net",
            source_url="https://augur.net/markets/fed-balance-sheet-2026",
            venue_type=VenueType.execution,
            canonical_event_id="augur_fed_balance_sheet_2026",
            liquidity=12_800.0,
            volume=24_000.0,
            tags=["macro", "rates"],
            categories=["economy"],
            probability=0.43,
            description="Bootstrap decentralized execution-like market",
        ),
        _bootstrap_market(
            venue=VenueName.augur,
            market_id="augur-oil-2026",
            title="Will oil close 2026 above $90?",
            question="Will oil close 2026 above $90?",
            slug="oil-2026",
            resolution_source="https://augur.net",
            source_url="https://augur.net/markets/oil-2026",
            venue_type=VenueType.execution,
            canonical_event_id="augur_oil_2026",
            liquidity=11_900.0,
            volume=22_500.0,
            tags=["macro", "commodities"],
            categories=["economy"],
            probability=0.39,
            description="Bootstrap decentralized execution-like market",
        ),
    ],
    notes=["execution-bindable bootstrap", "decentralized synthetic descriptors"],
)


OPINION_TRADE_PROFILE = AdditionalVenueProfile(
    venue=VenueName.opinion_trade,
    kind=AdditionalVenueKind.watchlist,
    backend_mode="bootstrap",
    bootstrap_role="watchlist_bootstrap",
    default_venue_type=VenueType.watchlist,
    qualified_venue_types={VenueType.signal, VenueType.watchlist},
    source_url="https://opinion.trade",
    planned_order_types=[],
    capabilities=VenueCapabilitiesModel(
        venue=VenueName.opinion_trade,
        discovery=True,
        metadata=True,
        orderbook=True,
        trades=True,
        positions=True,
        execution=False,
        streaming=False,
        interviews=False,
        read_only=True,
        supports_replay=True,
        metadata_map=_bootstrap_capability_metadata(
            backend_mode="bootstrap",
            venue_kind="watchlist",
            venue_type="watchlist",
            venue_taxonomy="watchlist_signal",
            tradeability_class="watchlist_paper_only",
            role_labels=["signal", "watchlist"],
            api_access=["catalog", "snapshot", "orderbook", "trades", "positions", "events", "evidence"],
            supported_order_types=[],
            read_only=True,
            paper_capable=True,
            execution_capable=False,
            positions_capable=True,
            events_capable=True,
            discovery_note="Watchlist discovery is available through bootstrap descriptors.",
            orderbook_note="Synthetic orderbook snapshots are available for watchlist planning only.",
            trades_note="Synthetic trade records are available for watchlist review.",
            execution_note="No live order placement is allowed for watchlist bootstrap venues.",
            websocket_note="No live websocket is exposed; snapshot feeds only.",
            paper_note="Paper mode is supported via watchlist bootstrap descriptors.",
            automation_constraints=["Read-only bootstrap profile.", "No live automation."],
            rate_limit_notes=["Bootstrap mode does not consume live venue rate limits."],
            execution_taxonomy="execution_like",
        ),
    ),
    metadata={
        "venue_type": "watchlist",
        "venue_taxonomy": "watchlist_signal",
        "tradeability_class": "watchlist_paper_only",
        "role_labels": ["signal", "watchlist"],
        "api_access": ["catalog", "snapshot", "orderbook", "trades", "positions", "events", "evidence"],
        "supported_order_types": [],
        "planned_order_types": [],
        "capability_notes": {
            "discovery": "Watchlist discovery is available for research.",
            "execution": "Read-only bootstrap profile; no live execution.",
        },
    },
    descriptors=[
        _bootstrap_market(
            venue=VenueName.opinion_trade,
            market_id="opinion-trade-election-2026",
            title="Will the 2026 election cycle stay close?",
            question="Will the 2026 election cycle stay close?",
            slug="election-2026",
            resolution_source="https://opinion.trade",
            source_url="https://opinion.trade/markets/election-2026",
            venue_type=VenueType.watchlist,
            canonical_event_id="opinion_trade_election_2026",
            liquidity=9_000.0,
            volume=19_000.0,
            tags=["politics", "election"],
            categories=["politics"],
            probability=0.51,
            description="Bootstrap watchlist market",
        ),
        _bootstrap_market(
            venue=VenueName.opinion_trade,
            market_id="opinion-trade-fed-cuts-2026",
            title="Will the Fed cut rates more than expected in 2026?",
            question="Will the Fed cut rates more than expected in 2026?",
            slug="fed-cuts-2026",
            resolution_source="https://opinion.trade",
            source_url="https://opinion.trade/markets/fed-cuts-2026",
            venue_type=VenueType.watchlist,
            canonical_event_id="opinion_trade_fed_cuts_2026",
            liquidity=8_500.0,
            volume=18_000.0,
            tags=["macro", "rates"],
            categories=["economy"],
            probability=0.48,
            description="Bootstrap watchlist market",
        ),
    ],
    notes=["watchlist bootstrap", "synthetic descriptors for contextual research"],
)


DEFAULT_ADDITIONAL_VENUE_MATRIX = VenueCapabilityMatrix(
    profiles=[
        MANIFOLD_PROFILE,
        METACULUS_PROFILE,
        ROBINHOOD_PROFILE,
        CRYPTOCOM_PROFILE,
        OMEN_PROFILE,
        AUGUR_PROFILE,
        OPINION_TRADE_PROFILE,
    ]
)


class BootstrapVenueAdapter:
    def __init__(self, profile: AdditionalVenueProfile) -> None:
        self.profile = profile
        self.venue = profile.venue
        self._descriptors = {descriptor.market_id: descriptor.model_copy(deep=True) for descriptor in profile.descriptors}

    def describe_capabilities(self) -> VenueCapabilitiesModel:
        return self.profile.capabilities.model_copy(deep=True)

    def list_markets(
        self,
        *,
        config: MarketUniverseConfig | None = None,
        limit: int | None = None,
    ) -> list[MarketDescriptor]:
        config = config or MarketUniverseConfig(venue=self.venue)
        if config.venue != self.venue:
            return []
        markets = [descriptor.model_copy(deep=True) for descriptor in self._descriptors.values()]
        if config.active_only:
            markets = [market for market in markets if market.status == MarketStatus.open]
        if config.query:
            query = config.query.lower()
            markets = [
                market
                for market in markets
                if query in market.title.lower() or query in market.question.lower() or query in (market.slug or "").lower()
            ]
        markets = [market for market in markets if market.liquidity is None or market.liquidity >= config.min_liquidity]
        markets = [market for market in markets if market.clarity_score >= config.min_clarity_score]
        allowed_statuses = set(config.statuses)
        markets = [market for market in markets if market.status in allowed_statuses]
        markets = sorted(markets, key=self._score_market, reverse=True)
        cap = limit if limit is not None else config.limit
        return markets[:cap]

    def get_market(self, market_id: str) -> MarketDescriptor:
        descriptor = self._descriptors.get(market_id)
        if descriptor is None:
            raise KeyError(f"Unknown bootstrap market for {self.venue.value}: {market_id}")
        return descriptor.model_copy(deep=True)

    def get_snapshot(self, market_id: str) -> MarketSnapshot:
        return _build_snapshot(self.get_market(market_id))

    def get_resolution_policy(self, market_id: str) -> ResolutionPolicy:
        return _build_policy(self.get_market(market_id))

    def get_trades(self, market_id: str) -> list[TradeRecord]:
        return [trade.model_copy(deep=True) for trade in _build_trades(self.get_market(market_id))]

    def get_events(self, market_id: str) -> list[MarketDescriptor]:
        _ = market_id
        return _event_markets(self.list_markets(limit=None))

    def get_positions(self, market_id: str) -> list[LedgerPosition]:
        return _load_position_records(self.venue, market_id)

    def get_evidence(self, market_id: str) -> list[EvidencePacket]:
        return [evidence.model_copy(deep=True) for evidence in _build_evidence(self.get_market(market_id))]

    def health(self) -> VenueHealthReport:
        return VenueHealthReport(
            venue=self.venue,
            backend_mode=self.profile.backend_mode,
            healthy=True,
            message=f"{self.venue.value} bootstrap available",
            details={
                "bootstrap": True,
                "profile_kind": self.profile.kind.value,
                "tradeability_class": self.profile.tradeability_class(),
                "venue_taxonomy": self.profile.venue_taxonomy(),
                "market_count": len(self._descriptors),
            },
        )

    @staticmethod
    def _score_market(market: MarketDescriptor) -> float:
        score = market.clarity_score
        if market.liquidity:
            score += min(0.2, market.liquidity / 100000.0)
        if market.status == MarketStatus.open:
            score += 0.05
        return score


class AdditionalVenueRegistry:
    def __init__(self, matrix: VenueCapabilityMatrix | None = None) -> None:
        self.matrix = matrix or DEFAULT_ADDITIONAL_VENUE_MATRIX
        self._adapters = {profile.venue: BootstrapVenueAdapter(profile) for profile in self.matrix.profiles}

    def list_venues(self) -> list[VenueName]:
        return self.matrix.venues()

    def list_profiles(self) -> list[AdditionalVenueProfile]:
        return [profile.model_copy(deep=True) for profile in self.matrix.profiles]

    def describe_matrix(self) -> VenueCapabilityMatrix:
        return self.matrix.model_copy(deep=True)

    def get_profile(self, venue: VenueName) -> AdditionalVenueProfile:
        profile = self.matrix.profile(venue)
        if profile is None:
            raise KeyError(f"Unsupported additional venue: {venue.value}")
        return profile.model_copy(deep=True)

    def get_adapter(self, venue: VenueName) -> BootstrapVenueAdapter:
        adapter = self._adapters.get(venue)
        if adapter is None:
            raise KeyError(f"Unsupported additional venue: {venue.value}")
        return adapter

    def list_markets(self, venue: VenueName, *, config: MarketUniverseConfig | None = None, limit: int | None = None) -> list[MarketDescriptor]:
        return self.get_adapter(venue).list_markets(config=config, limit=limit)

    def get_market(self, venue: VenueName, market_id: str) -> MarketDescriptor:
        return self.get_adapter(venue).get_market(market_id)

    def get_snapshot(self, venue: VenueName, market_id: str) -> MarketSnapshot:
        return self.get_adapter(venue).get_snapshot(market_id)

    def get_resolution_policy(self, venue: VenueName, market_id: str) -> ResolutionPolicy:
        return self.get_adapter(venue).get_resolution_policy(market_id)

    def get_trades(self, venue: VenueName, market_id: str) -> list[TradeRecord]:
        return self.get_adapter(venue).get_trades(market_id)

    def get_events(self, venue: VenueName, market_id: str) -> list[MarketDescriptor]:
        return self.get_adapter(venue).get_events(market_id)

    def get_positions(self, venue: VenueName, market_id: str) -> list[LedgerPosition]:
        return self.get_adapter(venue).get_positions(market_id)

    def get_evidence(self, venue: VenueName, market_id: str) -> list[EvidencePacket]:
        return self.get_adapter(venue).get_evidence(market_id)

    def health(self, venue: VenueName) -> VenueHealthReport:
        return self.get_adapter(venue).health()

    def qualifies_for(self, venue: VenueName, venue_type: VenueType) -> bool:
        return self.matrix.qualifies_for(venue, venue_type)

    def venues_for_role(self, venue_type: VenueType) -> list[VenueName]:
        return self.matrix.venues_for_role(venue_type)

    def role_classification(self) -> VenueRoleClassification:
        return self.matrix.role_classification()

    def execution_venues(self) -> list[VenueName]:
        return self.matrix.execution_venues()

    def reference_venues(self) -> list[VenueName]:
        return self.matrix.reference_venues()

    def signal_venues(self) -> list[VenueName]:
        return self.matrix.signal_venues()

    def watchlist_venues(self) -> list[VenueName]:
        return self.matrix.watchlist_venues()

    def execution_like_venues(self) -> list[VenueName]:
        return self.matrix.execution_like_venues()

    def execution_bindable_venues(self) -> list[VenueName]:
        return self.matrix.execution_bindable_venues()

    def execution_equivalent_venues(self) -> list[VenueName]:
        return self.matrix.execution_equivalent_venues()

    def execution_blocker_codes(self, venue: VenueName) -> list[str]:
        return self.matrix.execution_blocker_codes(venue)

    def read_only_venues(self) -> list[VenueName]:
        return self.matrix.read_only_venues()

    def paper_capable_venues(self) -> list[VenueName]:
        return self.matrix.paper_capable_venues()

    def execution_capable_venues(self) -> list[VenueName]:
        return self.matrix.execution_capable_venues()

    def positions_capable_venues(self) -> list[VenueName]:
        return self.matrix.positions_capable_venues()

    def events_capable_venues(self) -> list[VenueName]:
        return self.matrix.events_capable_venues()

    def paper_execution_like_venues(self) -> list[VenueName]:
        return self.matrix.paper_execution_like_venues()

    def venues_for_bootstrap_role(self, bootstrap_role: str) -> list[VenueName]:
        return self.matrix.venues_for_bootstrap_role(bootstrap_role)

    def venues_for_taxonomy(self, venue_taxonomy: str) -> list[VenueName]:
        return self.matrix.venues_for_taxonomy(venue_taxonomy)

    def tradeability_map(self) -> dict[str, str]:
        return self.matrix.tradeability_map()

    def qualification_map(self) -> dict[str, list[str]]:
        return self.matrix.qualification_map()

    def bootstrap_qualification_map(self) -> dict[str, dict[str, Any]]:
        return self.matrix.bootstrap_qualification_map()

    def bootstrap_qualified_venues(self) -> list[VenueName]:
        return self.matrix.bootstrap_qualified_venues()

    def bootstrap_tier_venues(self, tier: str = "tier_b") -> list[VenueName]:
        return self.matrix.bootstrap_tier_venues(tier)

    def role_counts(self) -> dict[str, int]:
        return self.matrix.role_counts()

    def surface_for(self, venue: VenueName) -> AdditionalVenueSurface:
        surface = self.matrix.surface_for(venue)
        if surface is None:
            raise KeyError(f"Unsupported additional venue: {venue.value}")
        return surface

    def surface_map(self) -> dict[str, AdditionalVenueSurface]:
        return self.matrix.surface_map()


def build_additional_venue_registry() -> AdditionalVenueRegistry:
    return AdditionalVenueRegistry()
