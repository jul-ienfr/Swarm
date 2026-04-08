from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .models import RunManifest, VenueCapabilitiesModel, VenueName, VenueType
from .paths import PredictionMarketPaths, default_prediction_market_paths


class VenueRoleClassification(BaseModel):
    schema_version: str = "v1"
    venue_roles: dict[str, list[str]] = Field(default_factory=dict)
    venue_types: dict[str, str] = Field(default_factory=dict)
    role_venues: dict[str, list[str]] = Field(default_factory=dict)
    role_counts: dict[str, int] = Field(default_factory=dict)
    bootstrap_qualified_venues: list[VenueName] = Field(default_factory=list)
    bootstrap_tier_b_venues: list[VenueName] = Field(default_factory=list)
    bootstrap_tier_b_count: int = 0
    bootstrap_roles: dict[str, str | None] = Field(default_factory=dict)
    execution_equivalent_venues: list[VenueName] = Field(default_factory=list)
    execution_bindable_venues: list[VenueName] = Field(default_factory=list)
    execution_like_venues: list[VenueName] = Field(default_factory=list)
    reference_only_venues: list[VenueName] = Field(default_factory=list)
    watchlist_only_venues: list[VenueName] = Field(default_factory=list)
    execution_equivalent_count: int = 0
    execution_bindable_count: int = 0
    execution_like_count: int = 0
    reference_only_count: int = 0
    watchlist_only_count: int = 0
    execution_taxonomy: dict[str, str] = Field(default_factory=dict)
    execution_taxonomy_counts: dict[str, int] = Field(default_factory=dict)
    execution_role: dict[str, str] = Field(default_factory=dict)
    execution_role_counts: dict[str, int] = Field(default_factory=dict)
    execution_pathway: dict[str, str] = Field(default_factory=dict)
    execution_pathway_counts: dict[str, int] = Field(default_factory=dict)
    readiness_stage: dict[str, str] = Field(default_factory=dict)
    readiness_stage_counts: dict[str, int] = Field(default_factory=dict)
    required_operator_action: dict[str, str] = Field(default_factory=dict)
    required_operator_action_counts: dict[str, int] = Field(default_factory=dict)
    bounded_execution_equivalent_venues: list[VenueName] = Field(default_factory=list)
    bounded_execution_equivalent_count: int = 0
    bounded_execution_promotion_candidate_venues: list[VenueName] = Field(default_factory=list)
    bounded_execution_promotion_candidate_count: int = 0
    execution_venues: list[VenueName] = Field(default_factory=list)
    reference_venues: list[VenueName] = Field(default_factory=list)
    signal_venues: list[VenueName] = Field(default_factory=list)
    watchlist_venues: list[VenueName] = Field(default_factory=list)
    read_only_venues: list[VenueName] = Field(default_factory=list)
    paper_capable_venues: list[VenueName] = Field(default_factory=list)
    execution_capable_venues: list[VenueName] = Field(default_factory=list)
    capability_notes: dict[str, dict[str, Any]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VenueExecutionCapability(BaseModel):
    schema_version: str = "v1"
    venue: VenueName
    adapter_name: str
    venue_type: VenueType | None = None
    bootstrap_tier: str | None = None
    bootstrap_role: str | None = None
    supports_discovery: bool = False
    supports_orderbook: bool = False
    supports_trades: bool = False
    supports_execution: bool = False
    supports_websocket: bool = False
    supports_paper_mode: bool = False
    api_access: list[str] = Field(default_factory=list)
    supported_order_types: list[str] = Field(default_factory=list)
    route_supported: bool = True
    dry_run_supported: bool = True
    live_execution_supported: bool = False
    bounded_execution_supported: bool = False
    market_execution_supported: bool = False
    order_audit_supported: bool = True
    fill_audit_supported: bool = True
    position_audit_supported: bool = True
    live_order_path: str | None = None
    bounded_order_path: str | None = None
    cancel_order_path: str | None = None
    qualified_venue_types: set[VenueType] = Field(default_factory=set)
    dry_run_requires_authorization: bool = False
    dry_run_requires_compliance: bool = False
    live_requires_authorization: bool = True
    live_requires_compliance: bool = True
    allowed_jurisdictions: set[str] = Field(default_factory=set)
    allowed_account_types: set[str] = Field(default_factory=set)
    automation_allowed: bool = True
    rate_limit_notes: list[str] = Field(default_factory=list)
    tos_notes: list[str] = Field(default_factory=list)
    discovery_notes: list[str] = Field(default_factory=list)
    orderbook_notes: list[str] = Field(default_factory=list)
    trades_notes: list[str] = Field(default_factory=list)
    execution_notes: list[str] = Field(default_factory=list)
    websocket_notes: list[str] = Field(default_factory=list)
    paper_notes: list[str] = Field(default_factory=list)
    automation_constraints: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def canonical_capabilities(self) -> VenueCapabilitiesModel:
        api_access = list(self.api_access or _api_access_for_capability(self))
        venue_taxonomy = VenueExecutionRegistry._venue_taxonomy_for_capability(self)
        execution_taxonomy = VenueExecutionRegistry._execution_taxonomy_for_capability(self)
        tradeability_class = self.metadata.get("tradeability_class")
        if not tradeability_class:
            tradeability_class = VenueExecutionRegistry._tradeability_class_for_capability(self)
        metadata_map = {
            **dict(self.metadata or {}),
            "venue_type": self.venue_type.value if self.venue_type else None,
            "venue_taxonomy": venue_taxonomy,
            "execution_taxonomy": execution_taxonomy,
            "tradeability_class": tradeability_class,
            "api_access": api_access,
            "supported_order_types": list(self.supported_order_types or _supported_order_types_for_capability(self)),
            "planned_order_types": list(self.metadata.get("planned_order_types") or _planned_order_types_for_capability(self)),
            "rate_limit_notes": list(self.rate_limit_notes),
            "automation_constraints": list(self.automation_constraints),
            "supports_discovery": self.supports_discovery,
            "supports_metadata": bool(self.metadata),
            "supports_orderbook": self.supports_orderbook,
            "supports_trades": self.supports_trades,
            "supports_positions": "positions" in api_access,
            "supports_execution": self.supports_execution,
            "supports_streaming": bool(
                self.supports_websocket
                or self.metadata.get("supports_market_feed")
                or self.metadata.get("supports_user_feed")
                or self.metadata.get("supports_rtds")
            ),
            "supports_websocket": self.supports_websocket,
            "supports_paper_mode": self.supports_paper_mode,
            "supports_interviews": bool(self.metadata.get("supports_interviews", False)),
            "supports_replay": True,
            "supports_events": "events" in api_access,
            "supports_market_feed": bool(self.metadata.get("supports_market_feed", self.supports_orderbook or self.supports_trades)),
            "supports_user_feed": bool(self.metadata.get("supports_user_feed", False)),
            "supports_rtds": bool(self.metadata.get("supports_rtds", False)),
            "read_only": not self.route_supported and not self.dry_run_supported and not self.live_execution_supported,
        }
        return VenueCapabilitiesModel(
            venue=self.venue,
            venue_type=self.venue_type,
            supports_discovery=self.supports_discovery,
            supports_metadata=bool(self.metadata),
            supports_orderbook=self.supports_orderbook,
            supports_trades=self.supports_trades,
            supports_positions="positions" in api_access,
            supports_execution=self.supports_execution,
            supports_streaming=bool(
                self.supports_websocket
                or self.metadata.get("supports_market_feed")
                or self.metadata.get("supports_user_feed")
                or self.metadata.get("supports_rtds")
            ),
            supports_websocket=self.supports_websocket,
            supports_paper_mode=self.supports_paper_mode,
            supports_interviews=bool(self.metadata.get("supports_interviews", False)),
            supports_replay=True,
            supports_events="events" in api_access,
            supports_market_feed=bool(self.metadata.get("supports_market_feed", self.supports_orderbook or self.supports_trades)),
            supports_user_feed=bool(self.metadata.get("supports_user_feed", False)),
            supports_rtds=bool(self.metadata.get("supports_rtds", False)),
            read_only=not self.route_supported and not self.dry_run_supported and not self.live_execution_supported,
            rate_limit_notes=list(self.rate_limit_notes),
            automation_constraints=list(self.automation_constraints),
            metadata_map=metadata_map,
        )

    def mode_for(self, *, dry_run: bool, allow_live_execution: bool, bounded_execution: bool | None = None) -> str:
        if dry_run:
            return "dry_run"
        if allow_live_execution and self.live_execution_supported:
            return "live"
        if bounded_execution is None:
            bounded_execution = self.bounded_execution_supported
        if bounded_execution:
            return "bounded_live"
        return "dry_run"

    def qualifies_for(self, venue_type: VenueType) -> bool:
        return venue_type in self.qualified_venue_types

    def primary_venue_type(self) -> VenueType | None:
        if not self.qualified_venue_types:
            return None
        return _ordered_venue_types(self.qualified_venue_types)[0]

    @model_validator(mode="after")
    def _hydrate_metadata(self) -> "VenueExecutionCapability":
        venue_types = [role.value for role in _ordered_venue_types(self.qualified_venue_types)]
        if self.venue_type is not None and self.venue_type.value not in venue_types:
            venue_types = [self.venue_type.value, *venue_types]
        self.api_access = list(self.api_access or _api_access_for_capability(self))
        self.supported_order_types = list(self.supported_order_types or _supported_order_types_for_capability(self))
        self.metadata.setdefault("venue_type", self.venue_type.value if self.venue_type else None)
        self.metadata.setdefault("bootstrap_tier", self.bootstrap_tier)
        self.metadata.setdefault("bootstrap_role", self.bootstrap_role)
        self.metadata.setdefault("supports_discovery", self.supports_discovery)
        self.metadata.setdefault("supports_orderbook", self.supports_orderbook)
        self.metadata.setdefault("supports_trades", self.supports_trades)
        self.metadata.setdefault("supports_execution", self.supports_execution)
        self.metadata.setdefault("supports_websocket", self.supports_websocket)
        self.metadata.setdefault("supports_paper_mode", self.supports_paper_mode)
        self.metadata.setdefault("qualified_venue_types", venue_types)
        self.metadata.setdefault("role_labels", venue_types)
        self.metadata.setdefault("api_access", _api_access_for_capability(self))
        self.metadata.setdefault("supported_order_types", _supported_order_types_for_capability(self))
        self.metadata.setdefault("planning_bucket", _planning_bucket_for_capability(self))
        self.metadata.setdefault("execution_equivalent", VenueExecutionRegistry._execution_equivalent_for_capability(self))
        self.metadata.setdefault("execution_like", VenueExecutionRegistry._execution_like_for_capability(self))
        self.metadata.setdefault("execution_taxonomy", VenueExecutionRegistry._execution_taxonomy_for_capability(self))
        self.metadata.setdefault("execution_role", VenueExecutionRegistry._execution_role_for_capability(self))
        self.metadata.setdefault("execution_pathway", VenueExecutionRegistry._execution_pathway_for_capability(self))
        self.metadata.setdefault("pathway_modes", VenueExecutionRegistry._pathway_modes_for_capability(self))
        self.metadata.setdefault("highest_actionable_mode", VenueExecutionRegistry._highest_actionable_mode_for_capability(self))
        self.metadata.setdefault("execution_blocker_codes", VenueExecutionRegistry._execution_blocker_codes_for_capability(self))
        self.metadata.setdefault("venue_taxonomy", VenueExecutionRegistry._venue_taxonomy_for_capability(self))
        self.metadata.setdefault("tradeability_class", VenueExecutionRegistry._tradeability_class_for_capability(self))
        self.metadata.setdefault("capability_notes", _capability_notes(self))
        self.metadata.setdefault("allowed_jurisdictions", sorted(self.allowed_jurisdictions))
        self.metadata.setdefault("allowed_account_types", sorted(self.allowed_account_types))
        self.metadata.setdefault("automation_allowed", self.automation_allowed)
        self.metadata.setdefault("automation_constraints", list(self.automation_constraints))
        self.metadata.setdefault("rate_limit_notes", list(self.rate_limit_notes))
        self.metadata.setdefault("tos_notes", list(self.tos_notes))
        self.metadata.setdefault(
            "order_paths",
            {
                "live": self.live_order_path,
                "bounded": self.bounded_order_path,
                "cancel": self.cancel_order_path,
            },
        )
        return self


class VenueExecutionSurface(BaseModel):
    schema_version: str = "v1"
    venue: VenueName
    adapter_name: str
    venue_type: VenueType | None = None
    bootstrap_tier: str | None = None
    bootstrap_role: str | None = None
    planning_bucket: str = "watchlist"
    status: str = "read_only"
    execution_readiness: str = "read_only"
    execution_role: str = "watchlist_only"
    execution_pathway: str = "read_only"
    execution_equivalent: bool = False
    execution_like: bool = False
    pathway_summary: str = ""
    operator_summary: str = ""
    promotion_summary: str = ""
    blocker_summary: str = ""
    supports_discovery: bool = False
    supports_orderbook: bool = False
    supports_trades: bool = False
    supports_execution: bool = False
    supports_websocket: bool = False
    supports_paper_mode: bool = False
    api_access: list[str] = Field(default_factory=list)
    supported_order_types: list[str] = Field(default_factory=list)
    rate_limit_notes: list[str] = Field(default_factory=list)
    automation_constraints: list[str] = Field(default_factory=list)
    route_supported: bool = True
    dry_run_supported: bool = True
    live_execution_supported: bool = False
    bounded_execution_supported: bool = False
    market_execution_supported: bool = False
    execution_taxonomy: str = "execution_like"
    read_only: bool = True
    paper_capable: bool = False
    execution_capable: bool = False
    live_order_path: str | None = None
    bounded_order_path: str | None = None
    cancel_order_path: str | None = None
    qualified_venue_types: list[str] = Field(default_factory=list)
    pathway_modes: list[str] = Field(default_factory=list)
    highest_actionable_mode: str | None = None
    required_operator_action: str = "no_order_routing"
    promotion_target_pathway: str | None = None
    promotion_rules: list[str] = Field(default_factory=list)
    pathway_ladder: list[str] = Field(default_factory=list)
    blocked_pathways: list[str] = Field(default_factory=list)
    promotion_rules_by_pathway: dict[str, list[str]] = Field(default_factory=dict)
    readiness_stage: str = "read_only"
    next_pathway: str | None = None
    next_pathway_rules: list[str] = Field(default_factory=list)
    bounded_execution_equivalent: bool = False
    bounded_execution_promotion_candidate: bool = False
    stage_summary: dict[str, Any] = Field(default_factory=dict)
    execution_blocker_codes: list[str] = Field(default_factory=list)
    capability_notes: dict[str, Any] = Field(default_factory=dict)
    mode_preview: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VenueAvailabilityReport(BaseModel):
    schema_version: str = "v1"
    venue: VenueName
    venue_type: str | None = None
    status: str = "unknown"
    execution_readiness: str = "read_only"
    execution_role: str = "watchlist_only"
    execution_pathway: str = "read_only"
    read_only: bool = True
    paper_capable: bool = False
    execution_capable: bool = False
    execution_equivalent: bool = False
    execution_like: bool = False
    pathway_summary: str = ""
    operator_summary: str = ""
    promotion_summary: str = ""
    blocker_summary: str = ""
    execution_taxonomy: str = "execution_like"
    supports_discovery: bool = False
    supports_orderbook: bool = False
    supports_trades: bool = False
    supports_execution: bool = False
    supports_websocket: bool = False
    supports_paper_mode: bool = False
    api_access: list[str] = Field(default_factory=list)
    supported_order_types: list[str] = Field(default_factory=list)
    pathway_modes: list[str] = Field(default_factory=list)
    highest_actionable_mode: str | None = None
    required_operator_action: str = "no_order_routing"
    promotion_target_pathway: str | None = None
    promotion_rules: list[str] = Field(default_factory=list)
    pathway_ladder: list[str] = Field(default_factory=list)
    blocked_pathways: list[str] = Field(default_factory=list)
    promotion_rules_by_pathway: dict[str, list[str]] = Field(default_factory=dict)
    readiness_stage: str = "read_only"
    next_pathway: str | None = None
    next_pathway_rules: list[str] = Field(default_factory=list)
    bounded_execution_equivalent: bool = False
    bounded_execution_promotion_candidate: bool = False
    stage_summary: dict[str, Any] = Field(default_factory=dict)
    execution_blocker_codes: list[str] = Field(default_factory=list)
    metadata_gap_count: int = 0
    metadata_gap_rate: float = 0.0
    availability_score: float = 0.0
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RegistryCoverageReport(BaseModel):
    schema_version: str = "v1"
    venue_count: int = 0
    execution_capable_count: int = 0
    paper_capable_count: int = 0
    read_only_count: int = 0
    degraded_venue_count: int = 0
    degraded_venue_rate: float = 0.0
    execution_equivalent_count: int = 0
    execution_like_count: int = 0
    reference_only_count: int = 0
    watchlist_only_count: int = 0
    execution_pathway_counts: dict[str, int] = Field(default_factory=dict)
    metadata_gap_count: int = 0
    metadata_gap_rate: float = 0.0
    execution_surface_rate: float = 0.0
    availability_by_venue: dict[str, VenueAvailabilityReport] = Field(default_factory=dict)
    role_counts: dict[str, int] = Field(default_factory=dict)
    execution_venues: list[VenueName] = Field(default_factory=list)
    paper_capable_venues: list[VenueName] = Field(default_factory=list)
    read_only_venues: list[VenueName] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VenueExecutionRegistry(BaseModel):
    schema_version: str = "v1"
    capabilities: list[VenueExecutionCapability] = Field(default_factory=list)

    def capability_for(self, venue: VenueName) -> VenueExecutionCapability:
        for capability in self.capabilities:
            if capability.venue == venue:
                return capability
        return VenueExecutionCapability(
            venue=venue,
            adapter_name=f"{venue.value}_execution_adapter",
            supports_discovery=False,
            supports_orderbook=False,
            supports_trades=False,
            supports_execution=False,
            supports_websocket=False,
            supports_paper_mode=False,
            route_supported=False,
            dry_run_supported=False,
            live_execution_supported=False,
            bounded_execution_supported=False,
            market_execution_supported=False,
            qualified_venue_types=set(),
            metadata={
                "backend_mode": "unregistered",
                "api_access": [],
                "supported_order_types": [],
                "supports_discovery": False,
                "supports_orderbook": False,
                "supports_trades": False,
                "supports_execution": False,
                "supports_websocket": False,
                "supports_paper_mode": False,
            },
        )

    def execution_surface(self, venue: VenueName) -> VenueExecutionSurface:
        capability = self.capability_for(venue)
        paper_capable = self.is_paper_capable(venue)
        execution_capable = self.is_execution_capable(venue)
        read_only = self.is_read_only(venue)
        planning_bucket = self._planning_bucket_for_capability(capability)
        execution_readiness = self._execution_readiness_for_capability(capability, planning_bucket)
        execution_like = self._execution_like_for_capability(capability)
        execution_role = self._execution_role_for_capability(capability)
        execution_pathway = self._execution_pathway_for_capability(capability)
        pathway_modes = self._pathway_modes_for_capability(capability)
        highest_actionable_mode = self._highest_actionable_mode_for_capability(capability)
        required_operator_action = self._required_operator_action_for_capability(capability)
        promotion_target_pathway = self._promotion_target_pathway_for_capability(capability)
        promotion_rules = self._promotion_rules_for_capability(capability)
        pathway_ladder = self._pathway_ladder_for_capability(capability)
        blocked_pathways = self._blocked_pathways_for_capability(capability)
        promotion_rules_by_pathway = self._promotion_rules_by_pathway_for_capability(capability)
        readiness_stage = self._readiness_stage_for_capability(capability)
        next_pathway = self._next_pathway_for_capability(capability)
        next_pathway_rules = self._next_pathway_rules_for_capability(capability)
        bounded_execution_equivalent = self._bounded_execution_equivalent_for_capability(capability)
        bounded_execution_promotion_candidate = self._bounded_execution_promotion_candidate_for_capability(capability)
        stage_summary = self._stage_summary_for_capability(capability)
        execution_blocker_codes = self._execution_blocker_codes_for_capability(capability)
        stage_summary = dict(stage_summary)
        pathway_summary = str(stage_summary.get("pathway_summary") or self._pathway_summary_for_capability(capability))
        operator_summary = str(stage_summary.get("operator_summary") or self._operator_summary_for_capability(capability))
        promotion_summary = str(stage_summary.get("promotion_summary") or self._promotion_summary_for_capability(capability))
        blocker_summary = str(stage_summary.get("blocker_summary") or self._blocker_summary_for_capability(capability))
        qualified_types = [role.value for role in _ordered_venue_types(capability.qualified_venue_types)]
        if capability.venue_type is not None and capability.venue_type.value not in qualified_types:
            qualified_types = [capability.venue_type.value, *qualified_types]
        if capability.live_execution_supported:
            status = "live"
        elif capability.bounded_execution_supported or capability.market_execution_supported:
            status = "bounded_live"
        elif VenueExecutionRegistry._execution_bindable_for_capability(capability):
            status = "execution_bindable"
        elif capability.dry_run_supported or paper_capable:
            status = "paper_ready"
        else:
            status = "read_only"
        execution_equivalent = self._execution_equivalent_for_capability(capability)
        tradeability_class = self._tradeability_class_for_capability(capability)
        venue_taxonomy = self._venue_taxonomy_for_capability(capability)
        execution_taxonomy = self._execution_taxonomy_for_capability(capability)
        return VenueExecutionSurface(
            venue=venue,
            adapter_name=capability.adapter_name,
            venue_type=capability.venue_type,
            bootstrap_tier=capability.bootstrap_tier,
            bootstrap_role=capability.bootstrap_role,
            planning_bucket=planning_bucket,
            status=status,
            execution_readiness=execution_readiness,
            execution_role=execution_role,
            execution_pathway=execution_pathway,
            execution_equivalent=execution_equivalent,
            execution_like=execution_like,
            pathway_summary=pathway_summary,
            operator_summary=operator_summary,
            promotion_summary=promotion_summary,
            blocker_summary=blocker_summary,
            supports_discovery=capability.supports_discovery,
            supports_orderbook=capability.supports_orderbook,
            supports_trades=capability.supports_trades,
            supports_execution=capability.supports_execution,
            supports_websocket=capability.supports_websocket,
            supports_paper_mode=capability.supports_paper_mode,
            api_access=list(capability.api_access or _api_access_for_capability(capability)),
            supported_order_types=list(
                capability.supported_order_types or _supported_order_types_for_capability(capability)
            ),
            rate_limit_notes=list(capability.rate_limit_notes),
            automation_constraints=list(capability.automation_constraints),
            route_supported=capability.route_supported,
            dry_run_supported=capability.dry_run_supported,
            live_execution_supported=capability.live_execution_supported,
            bounded_execution_supported=capability.bounded_execution_supported,
            market_execution_supported=capability.market_execution_supported,
            execution_taxonomy=execution_taxonomy,
            read_only=read_only,
            paper_capable=paper_capable,
            execution_capable=execution_capable,
            live_order_path=capability.live_order_path,
            bounded_order_path=capability.bounded_order_path,
            cancel_order_path=capability.cancel_order_path,
            qualified_venue_types=qualified_types,
            pathway_modes=pathway_modes,
            highest_actionable_mode=highest_actionable_mode,
            required_operator_action=required_operator_action,
            promotion_target_pathway=promotion_target_pathway,
            promotion_rules=promotion_rules,
            pathway_ladder=pathway_ladder,
            blocked_pathways=blocked_pathways,
            promotion_rules_by_pathway=promotion_rules_by_pathway,
            readiness_stage=readiness_stage,
            next_pathway=next_pathway,
            next_pathway_rules=next_pathway_rules,
            bounded_execution_equivalent=bounded_execution_equivalent,
            bounded_execution_promotion_candidate=bounded_execution_promotion_candidate,
            stage_summary=stage_summary,
            execution_blocker_codes=execution_blocker_codes,
            capability_notes=_capability_notes(capability),
            mode_preview={
                "dry_run": capability.mode_for(dry_run=True, allow_live_execution=False, bounded_execution=False),
                "bounded": capability.mode_for(dry_run=False, allow_live_execution=False, bounded_execution=True),
                "live": capability.mode_for(dry_run=False, allow_live_execution=True, bounded_execution=False),
            },
            metadata={
                **dict(capability.metadata),
                "bootstrap_tier": capability.bootstrap_tier,
                "bootstrap_role": capability.bootstrap_role,
                "planning_bucket": planning_bucket,
                "execution_equivalent": execution_equivalent,
                "execution_like": execution_like,
                "pathway_summary": pathway_summary,
                "operator_summary": operator_summary,
                "promotion_summary": promotion_summary,
                "blocker_summary": blocker_summary,
                "execution_taxonomy": execution_taxonomy,
                "execution_role": execution_role,
                "execution_pathway": execution_pathway,
                "pathway_modes": list(pathway_modes),
                "highest_actionable_mode": highest_actionable_mode,
                "required_operator_action": required_operator_action,
                "promotion_target_pathway": promotion_target_pathway,
                "promotion_rules": list(promotion_rules),
                "pathway_ladder": list(pathway_ladder),
                "blocked_pathways": list(blocked_pathways),
                "promotion_rules_by_pathway": {
                    key: list(value)
                    for key, value in promotion_rules_by_pathway.items()
                },
                "readiness_stage": readiness_stage,
                "next_pathway": next_pathway,
                "next_pathway_rules": list(next_pathway_rules),
                "bounded_execution_equivalent": bounded_execution_equivalent,
                "bounded_execution_promotion_candidate": bounded_execution_promotion_candidate,
                "stage_summary": dict(stage_summary),
                "manual_execution_contract": dict(stage_summary.get("manual_execution_contract", {})),
                "promotion_ladder": [dict(step) for step in stage_summary.get("promotion_ladder", [])],
                "execution_blocker_codes": list(execution_blocker_codes),
                "pathway_summary": pathway_summary,
                "operator_summary": operator_summary,
                "promotion_summary": promotion_summary,
                "blocker_summary": blocker_summary,
                "tradeability_class": tradeability_class,
                "venue_taxonomy": venue_taxonomy,
                "execution_readiness": execution_readiness,
                "paper_capable": paper_capable,
                "execution_capable": execution_capable,
                "read_only": read_only,
                "surface_status": status,
                "supports_discovery": capability.supports_discovery,
                "supports_orderbook": capability.supports_orderbook,
                "supports_trades": capability.supports_trades,
                "supports_execution": capability.supports_execution,
                "supports_websocket": capability.supports_websocket,
                "supports_paper_mode": capability.supports_paper_mode,
                "api_access": list(capability.api_access or _api_access_for_capability(capability)),
                "supported_order_types": list(
                    capability.supported_order_types or _supported_order_types_for_capability(capability)
                ),
                "planned_order_types": list(capability.metadata.get("planned_order_types") or _planned_order_types_for_capability(capability)),
                "rate_limit_notes": list(capability.rate_limit_notes),
                "automation_constraints": list(capability.automation_constraints),
                "order_paths": {
                    "live": capability.live_order_path,
                    "bounded": capability.bounded_order_path,
                    "cancel": capability.cancel_order_path,
                },
            },
        )

    def execution_readiness_map(self) -> dict[str, dict[str, Any]]:
        return {
            capability.venue.value: {
                "bootstrap_tier": capability.bootstrap_tier,
                "bootstrap_role": capability.bootstrap_role,
                "planning_bucket": self._planning_bucket_for_capability(capability),
                "surface_status": self.execution_surface(capability.venue).status,
                "execution_readiness": self.execution_surface(capability.venue).execution_readiness,
                "execution_equivalent": self._execution_equivalent_for_capability(capability),
                "execution_like": self._execution_like_for_capability(capability),
                "execution_role": self._execution_role_for_capability(capability),
                "execution_pathway": self._execution_pathway_for_capability(capability),
                "pathway_modes": self._pathway_modes_for_capability(capability),
                "highest_actionable_mode": self._highest_actionable_mode_for_capability(capability),
                "required_operator_action": self._required_operator_action_for_capability(capability),
                "promotion_target_pathway": self._promotion_target_pathway_for_capability(capability),
                "promotion_rules": self._promotion_rules_for_capability(capability),
                "pathway_ladder": self._pathway_ladder_for_capability(capability),
                "blocked_pathways": self._blocked_pathways_for_capability(capability),
                "promotion_rules_by_pathway": self._promotion_rules_by_pathway_for_capability(capability),
                "manual_execution_contract": self._manual_execution_contract_for_capability(capability),
                "promotion_ladder": self._manual_execution_contract_for_capability(capability).get("promotion_steps", []),
                "pathway_summary": self._pathway_summary_for_capability(capability),
                "operator_summary": self._operator_summary_for_capability(capability),
                "promotion_summary": self._promotion_summary_for_capability(capability),
                "blocker_summary": self._blocker_summary_for_capability(capability),
                "readiness_stage": self._readiness_stage_for_capability(capability),
                "next_pathway": self._next_pathway_for_capability(capability),
                "next_pathway_rules": self._next_pathway_rules_for_capability(capability),
                "bounded_execution_equivalent": self._bounded_execution_equivalent_for_capability(capability),
                "bounded_execution_promotion_candidate": self._bounded_execution_promotion_candidate_for_capability(capability),
                "credential_gate": self._credential_gate_for_capability(capability),
                "api_gate": self._api_gate_for_capability(capability),
                "adapter_readiness": self._adapter_readiness_for_capability(capability),
                "execution_requirement_codes": self._execution_requirement_codes_for_capability(capability),
                "missing_requirement_codes": self._missing_requirement_codes_for_capability(capability),
                "missing_requirement_count": len(self._missing_requirement_codes_for_capability(capability)),
                "operator_ready_now": bool(self._stage_summary_for_capability(capability).get("operator_ready_now", False)),
                "operator_checklist": self._operator_checklist_for_capability(capability),
                "promotion_evidence_by_pathway": self._promotion_evidence_by_pathway_for_capability(capability),
                "execution_blocker_codes": self._execution_blocker_codes_for_capability(capability),
                "tradeability_class": self._tradeability_class_for_capability(capability),
                "venue_taxonomy": self._venue_taxonomy_for_capability(capability),
                "supports_discovery": capability.supports_discovery,
                "supports_orderbook": capability.supports_orderbook,
                "supports_trades": capability.supports_trades,
                "supports_execution": capability.supports_execution,
                "supports_websocket": capability.supports_websocket,
                "supports_paper_mode": capability.supports_paper_mode,
                "read_only": self.is_read_only(capability.venue),
                "paper_capable": self.is_paper_capable(capability.venue),
                "execution_capable": self.is_execution_capable(capability.venue),
                "live_execution_supported": capability.live_execution_supported,
                "bounded_execution_supported": capability.bounded_execution_supported,
                "market_execution_supported": capability.market_execution_supported,
                "api_access": _api_access_for_capability(capability),
                "supported_order_types": _supported_order_types_for_capability(capability),
                "planned_order_types": _planned_order_types_for_capability(capability),
                "qualified_venue_types": [role.value for role in _ordered_venue_types(capability.qualified_venue_types)],
            }
            for capability in self.capabilities
        }

    def execution_surface_map(self) -> dict[str, VenueExecutionSurface]:
        return {capability.venue.value: self.execution_surface(capability.venue) for capability in self.capabilities}

    def execution_pathway(self, venue: VenueName) -> str:
        return self.execution_surface(venue).execution_pathway

    def execution_blocker_codes(self, venue: VenueName) -> list[str]:
        return self.execution_surface(venue).execution_blocker_codes

    def required_operator_action(self, venue: VenueName) -> str:
        return self.execution_surface(venue).required_operator_action

    def promotion_target_pathway(self, venue: VenueName) -> str | None:
        return self.execution_surface(venue).promotion_target_pathway

    def promotion_rules(self, venue: VenueName) -> list[str]:
        return self.execution_surface(venue).promotion_rules

    def canonical_capabilities(self, venue: VenueName) -> VenueCapabilitiesModel:
        return self.capability_for(venue).canonical_capabilities()

    def supports_live_execution(self, venue: VenueName) -> bool:
        return self.capability_for(venue).live_execution_supported

    def supports_bounded_execution(self, venue: VenueName) -> bool:
        return self.capability_for(venue).bounded_execution_supported

    def supports_dry_run(self, venue: VenueName) -> bool:
        return self.capability_for(venue).dry_run_supported

    def supports_discovery(self, venue: VenueName) -> bool:
        return self.capability_for(venue).supports_discovery

    def supports_orderbook(self, venue: VenueName) -> bool:
        return self.capability_for(venue).supports_orderbook

    def supports_trades(self, venue: VenueName) -> bool:
        return self.capability_for(venue).supports_trades

    def supports_execution(self, venue: VenueName) -> bool:
        return self.capability_for(venue).supports_execution

    def supports_websocket(self, venue: VenueName) -> bool:
        return self.capability_for(venue).supports_websocket

    def supports_paper_mode(self, venue: VenueName) -> bool:
        return self.capability_for(venue).supports_paper_mode

    def is_read_only(self, venue: VenueName) -> bool:
        capability = self.capability_for(venue)
        return not capability.route_supported and not capability.dry_run_supported and not capability.live_execution_supported

    def is_paper_capable(self, venue: VenueName) -> bool:
        capability = self.capability_for(venue)
        return capability.dry_run_supported or capability.bounded_execution_supported or capability.market_execution_supported

    def is_execution_capable(self, venue: VenueName) -> bool:
        capability = self.capability_for(venue)
        return capability.live_execution_supported or capability.bounded_execution_supported or capability.market_execution_supported

    def qualifies_for(self, venue: VenueName, venue_type: VenueType) -> bool:
        return self.capability_for(venue).qualifies_for(venue_type)

    def venues_for_role(self, venue_type: VenueType) -> list[VenueName]:
        return [capability.venue for capability in self.capabilities if capability.qualifies_for(venue_type)]

    def execution_venues(self) -> list[VenueName]:
        return self.venues_for_role(VenueType.execution)

    def execution_equivalent_venues(self) -> list[VenueName]:
        return [capability.venue for capability in self.capabilities if self.execution_surface(capability.venue).execution_equivalent]

    def execution_bindable_venues(self) -> list[VenueName]:
        return [capability.venue for capability in self.capabilities if self._execution_bindable_for_capability(capability)]

    def execution_like_venues(self) -> list[VenueName]:
        return [capability.venue for capability in self.capabilities if self._execution_like_for_capability(capability)]

    def paper_execution_like_venues(self) -> list[VenueName]:
        return [
            capability.venue
            for capability in self.capabilities
            if self._tradeability_class_for_capability(capability) in {"execution_like_paper_only", "execution_bindable_dry_run"}
        ]

    def venues_for_bootstrap_role(self, bootstrap_role: str) -> list[VenueName]:
        normalized = str(bootstrap_role).strip().lower()
        return [
            capability.venue
            for capability in self.capabilities
            if str(capability.bootstrap_role or "").strip().lower() == normalized
        ]

    def tradeability_map(self) -> dict[str, str]:
        return {
            capability.venue.value: self._tradeability_class_for_capability(capability)
            for capability in self.capabilities
        }

    def reference_venues(self) -> list[VenueName]:
        return self.venues_for_role(VenueType.reference)

    def reference_only_venues(self) -> list[VenueName]:
        return self.reference_venues()

    def signal_venues(self) -> list[VenueName]:
        return self.venues_for_role(VenueType.signal)

    def watchlist_venues(self) -> list[VenueName]:
        return self.venues_for_role(VenueType.watchlist)

    def watchlist_only_venues(self) -> list[VenueName]:
        return [capability.venue for capability in self.capabilities if self._planning_bucket_for_capability(capability) == "watchlist"]

    def bootstrap_qualified_venues(self) -> list[VenueName]:
        return [capability.venue for capability in self.capabilities if capability.bootstrap_tier == "tier_b"]

    def bootstrap_tier_venues(self, tier: str = "tier_b") -> list[VenueName]:
        return [capability.venue for capability in self.capabilities if capability.bootstrap_tier == tier]

    def bootstrap_qualification_map(self) -> dict[str, dict[str, Any]]:
        return {
            capability.venue.value: {
                "bootstrap_tier": capability.bootstrap_tier,
                "bootstrap_role": capability.bootstrap_role,
                "venue_type": capability.venue_type.value if capability.venue_type else None,
                "planning_bucket": self._planning_bucket_for_capability(capability),
                "execution_equivalent": self.execution_surface(capability.venue).execution_equivalent,
                "execution_like": self._execution_like_for_capability(capability),
                "execution_taxonomy": self._execution_taxonomy_for_capability(capability),
                "execution_role": self._execution_role_for_capability(capability),
                "execution_pathway": self._execution_pathway_for_capability(capability),
                "pathway_modes": self._pathway_modes_for_capability(capability),
                "highest_actionable_mode": self._highest_actionable_mode_for_capability(capability),
                "required_operator_action": self._required_operator_action_for_capability(capability),
                "promotion_target_pathway": self._promotion_target_pathway_for_capability(capability),
                "promotion_rules": self._promotion_rules_for_capability(capability),
                "pathway_ladder": self._pathway_ladder_for_capability(capability),
                "blocked_pathways": self._blocked_pathways_for_capability(capability),
                "promotion_rules_by_pathway": self._promotion_rules_by_pathway_for_capability(capability),
                "manual_execution_contract": self._manual_execution_contract_for_capability(capability),
                "promotion_ladder": self._manual_execution_contract_for_capability(capability).get("promotion_steps", []),
                "pathway_summary": self._pathway_summary_for_capability(capability),
                "operator_summary": self._operator_summary_for_capability(capability),
                "promotion_summary": self._promotion_summary_for_capability(capability),
                "blocker_summary": self._blocker_summary_for_capability(capability),
                "readiness_stage": self._readiness_stage_for_capability(capability),
                "next_pathway": self._next_pathway_for_capability(capability),
                "next_pathway_rules": self._next_pathway_rules_for_capability(capability),
                "bounded_execution_equivalent": self._bounded_execution_equivalent_for_capability(capability),
                "bounded_execution_promotion_candidate": self._bounded_execution_promotion_candidate_for_capability(capability),
                "credential_gate": self._credential_gate_for_capability(capability),
                "api_gate": self._api_gate_for_capability(capability),
                "adapter_readiness": self._adapter_readiness_for_capability(capability),
                "execution_requirement_codes": self._execution_requirement_codes_for_capability(capability),
                "missing_requirement_codes": self._missing_requirement_codes_for_capability(capability),
                "missing_requirement_count": len(self._missing_requirement_codes_for_capability(capability)),
                "operator_ready_now": bool(self._stage_summary_for_capability(capability).get("operator_ready_now", False)),
                "operator_checklist": self._operator_checklist_for_capability(capability),
                "promotion_evidence_by_pathway": self._promotion_evidence_by_pathway_for_capability(capability),
                "execution_blocker_codes": self._execution_blocker_codes_for_capability(capability),
                "tradeability_class": self._tradeability_class_for_capability(capability),
                "venue_taxonomy": self._venue_taxonomy_for_capability(capability),
                "execution_taxonomy": self._execution_taxonomy_for_capability(capability),
                "execution_readiness": self.execution_surface(capability.venue).execution_readiness,
                "surface_status": self.execution_surface(capability.venue).status,
                "read_only": self.is_read_only(capability.venue),
                "paper_capable": self.is_paper_capable(capability.venue),
                "execution_capable": self.is_execution_capable(capability.venue),
                "supports_discovery": capability.supports_discovery,
                "supports_orderbook": capability.supports_orderbook,
                "supports_trades": capability.supports_trades,
                "supports_execution": capability.supports_execution,
                "supports_websocket": capability.supports_websocket,
                "supports_paper_mode": capability.supports_paper_mode,
                "route_supported": capability.route_supported,
                "live_execution_supported": capability.live_execution_supported,
                "bounded_execution_supported": capability.bounded_execution_supported,
                "market_execution_supported": capability.market_execution_supported,
                "api_access": _api_access_for_capability(capability),
                "supported_order_types": _supported_order_types_for_capability(capability),
                "planned_order_types": _planned_order_types_for_capability(capability),
                "qualified_venue_types": [role.value for role in _ordered_venue_types(capability.qualified_venue_types)],
            }
            for capability in self.capabilities
        }

    def read_only_venues(self) -> list[VenueName]:
        return [capability.venue for capability in self.capabilities if self.is_read_only(capability.venue)]

    def paper_capable_venues(self) -> list[VenueName]:
        return [capability.venue for capability in self.capabilities if self.is_paper_capable(capability.venue)]

    def execution_capable_venues(self) -> list[VenueName]:
        return [capability.venue for capability in self.capabilities if self.is_execution_capable(capability.venue)]

    def qualification_map(self) -> dict[str, list[str]]:
        return {capability.venue.value: [role.value for role in _ordered_venue_types(capability.qualified_venue_types)] for capability in self.capabilities}

    def role_classification(self) -> VenueRoleClassification:
        venue_roles: dict[str, list[str]] = {}
        venue_types: dict[str, str] = {}
        role_venues: dict[str, list[str]] = {}
        role_counts: dict[str, int] = {}
        planning_bucket_map: dict[str, str] = {}
        bootstrap_tier_map: dict[str, str | None] = {}
        bootstrap_role_map: dict[str, str | None] = {}
        execution_role_map: dict[str, str] = {}
        execution_taxonomy_map: dict[str, str] = {}
        manual_execution_contracts_map: dict[str, dict[str, Any]] = {}
        promotion_ladders_map: dict[str, list[dict[str, Any]]] = {}
        execution_equivalent_venues: list[VenueName] = []
        execution_bindable_venues: list[VenueName] = []
        execution_like_venues: list[VenueName] = []
        reference_only_venues: list[VenueName] = []
        watchlist_only_venues: list[VenueName] = []
        for capability in self.capabilities:
            roles = [role.value for role in _ordered_venue_types(capability.qualified_venue_types)]
            venue_roles[capability.venue.value] = roles
            venue_types[capability.venue.value] = capability.venue_type.value if capability.venue_type else (roles[0] if roles else VenueType.watchlist.value)
            bootstrap_tier_map[capability.venue.value] = capability.bootstrap_tier
            bootstrap_role_map[capability.venue.value] = capability.bootstrap_role
            execution_role_map[capability.venue.value] = self._execution_role_for_capability(capability)
            execution_taxonomy_map[capability.venue.value] = self._execution_taxonomy_for_capability(capability)
            manual_execution_contracts_map[capability.venue.value] = self._manual_execution_contract_for_capability(capability)
            promotion_ladders_map[capability.venue.value] = [
                dict(step)
                for step in self._manual_execution_contract_for_capability(capability).get("promotion_steps", [])
            ]
            planning_bucket = self._planning_bucket_for_capability(capability)
            planning_bucket_map[capability.venue.value] = planning_bucket
            if self._execution_equivalent_for_capability(capability):
                execution_equivalent_venues.append(capability.venue)
            elif self._execution_bindable_for_capability(capability):
                execution_bindable_venues.append(capability.venue)
            elif planning_bucket == "reference-only":
                reference_only_venues.append(capability.venue)
            elif self._execution_like_for_capability(capability):
                execution_like_venues.append(capability.venue)
            else:
                watchlist_only_venues.append(capability.venue)
            for role in roles:
                role_counts[role] = role_counts.get(role, 0) + 1
                role_venues.setdefault(role, [])
                if capability.venue.value not in role_venues[role]:
                    role_venues[role].append(capability.venue.value)
        for venues in role_venues.values():
            venues.sort()
        execution_equivalent_venues = list(dict.fromkeys(execution_equivalent_venues))
        execution_bindable_venues = list(dict.fromkeys(execution_bindable_venues))
        execution_like_venues = list(dict.fromkeys(execution_like_venues))
        reference_only_venues = list(dict.fromkeys(reference_only_venues))
        watchlist_only_venues = list(dict.fromkeys(watchlist_only_venues))
        execution_role_counts = {
            role: sum(1 for value in execution_role_map.values() if value == role)
            for role in sorted({*execution_role_map.values()})
        }
        execution_pathway_map = {
            capability.venue.value: self._execution_pathway_for_capability(capability)
            for capability in self.capabilities
        }
        execution_pathway_counts = {
            pathway: sum(1 for value in execution_pathway_map.values() if value == pathway)
            for pathway in sorted({*execution_pathway_map.values()})
        }
        readiness_stage_map = {
            capability.venue.value: self._readiness_stage_for_capability(capability)
            for capability in self.capabilities
        }
        readiness_stage_counts = {
            stage: sum(1 for value in readiness_stage_map.values() if value == stage)
            for stage in sorted({*readiness_stage_map.values()})
        }
        required_operator_action_map = {
            capability.venue.value: self._required_operator_action_for_capability(capability)
            for capability in self.capabilities
        }
        required_operator_action_counts = {
            action: sum(1 for value in required_operator_action_map.values() if value == action)
            for action in sorted({*required_operator_action_map.values()})
        }
        bounded_execution_equivalent_venues = [
            capability.venue
            for capability in self.capabilities
            if self._bounded_execution_equivalent_for_capability(capability)
        ]
        bounded_execution_promotion_candidate_venues = [
            capability.venue
            for capability in self.capabilities
            if self._bounded_execution_promotion_candidate_for_capability(capability)
        ]
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
            execution_taxonomy=execution_taxonomy_map,
            execution_taxonomy_counts={
                taxonomy: sum(1 for value in execution_taxonomy_map.values() if value == taxonomy)
                for taxonomy in sorted({*execution_taxonomy_map.values()})
            },
            execution_role=execution_role_map,
            execution_role_counts=execution_role_counts,
            execution_pathway=execution_pathway_map,
            execution_pathway_counts=execution_pathway_counts,
            readiness_stage=readiness_stage_map,
            readiness_stage_counts=readiness_stage_counts,
            required_operator_action=required_operator_action_map,
            required_operator_action_counts=required_operator_action_counts,
            bounded_execution_equivalent_venues=bounded_execution_equivalent_venues,
            bounded_execution_equivalent_count=len(bounded_execution_equivalent_venues),
            bounded_execution_promotion_candidate_venues=bounded_execution_promotion_candidate_venues,
            bounded_execution_promotion_candidate_count=len(bounded_execution_promotion_candidate_venues),
            bootstrap_qualified_venues=self.bootstrap_qualified_venues(),
            bootstrap_tier_b_venues=self.bootstrap_tier_venues(),
            bootstrap_tier_b_count=len(self.bootstrap_tier_venues("tier_b")),
            bootstrap_roles=bootstrap_role_map,
            execution_venues=self.execution_venues(),
            reference_venues=self.reference_venues(),
            signal_venues=self.signal_venues(),
            watchlist_venues=self.watchlist_venues(),
            read_only_venues=self.read_only_venues(),
            paper_capable_venues=self.paper_capable_venues(),
            execution_capable_venues=self.execution_capable_venues(),
            capability_notes={capability.venue.value: _capability_notes(capability) for capability in self.capabilities},
            metadata={
                "venue_count": len(self.capabilities),
                "execution_capable_count": len(self.execution_capable_venues()),
                "paper_capable_count": len(self.paper_capable_venues()),
                "read_only_count": len(self.read_only_venues()),
                "execution_equivalent_count": len(execution_equivalent_venues),
                "execution_bindable_count": len(execution_bindable_venues),
                "execution_like_count": len(execution_like_venues),
                "reference_only_count": len(reference_only_venues),
                "watchlist_only_count": len(watchlist_only_venues),
                "execution_taxonomy": execution_taxonomy_map,
                "execution_taxonomy_counts": {
                    taxonomy: sum(1 for value in execution_taxonomy_map.values() if value == taxonomy)
                    for taxonomy in sorted({*execution_taxonomy_map.values()})
                },
                "execution_role": execution_role_map,
                "execution_role_counts": execution_role_counts,
                "manual_execution_contracts": manual_execution_contracts_map,
                "promotion_ladders": promotion_ladders_map,
                "execution_pathway": execution_pathway_map,
                "execution_pathway_counts": execution_pathway_counts,
                "readiness_stage": readiness_stage_map,
                "readiness_stage_counts": readiness_stage_counts,
                "required_operator_action": required_operator_action_map,
                "required_operator_action_counts": required_operator_action_counts,
                "bounded_execution_equivalent_venues": [
                    venue.value for venue in bounded_execution_equivalent_venues
                ],
                "bounded_execution_promotion_candidate_venues": [
                    venue.value for venue in bounded_execution_promotion_candidate_venues
                ],
                "credential_gate": {
                    capability.venue.value: self._credential_gate_for_capability(capability)
                    for capability in self.capabilities
                },
                "credential_gate_counts": {
                    gate: sum(
                        1 for capability in self.capabilities
                        if self._credential_gate_for_capability(capability) == gate
                    )
                    for gate in sorted({
                        self._credential_gate_for_capability(capability)
                        for capability in self.capabilities
                    })
                },
                "api_gate": {
                    capability.venue.value: self._api_gate_for_capability(capability)
                    for capability in self.capabilities
                },
                "api_gate_counts": {
                    gate: sum(
                        1 for capability in self.capabilities
                        if self._api_gate_for_capability(capability) == gate
                    )
                    for gate in sorted({
                        self._api_gate_for_capability(capability)
                        for capability in self.capabilities
                    })
                },
                "missing_requirement_count_by_venue": {
                    capability.venue.value: len(self._missing_requirement_codes_for_capability(capability))
                    for capability in self.capabilities
                },
                "operator_ready_now": {
                    capability.venue.value: bool(self._stage_summary_for_capability(capability).get("operator_ready_now", False))
                    for capability in self.capabilities
                },
                "operator_ready_count": sum(
                    1
                    for capability in self.capabilities
                    if self._stage_summary_for_capability(capability).get("operator_ready_now", False)
                ),
                "promotion_target_pathway": {
                    capability.venue.value: self._promotion_target_pathway_for_capability(capability)
                    for capability in self.capabilities
                },
                "promotion_rules": {
                    capability.venue.value: self._promotion_rules_for_capability(capability)
                    for capability in self.capabilities
                },
                "pathway_ladder": {
                    capability.venue.value: self._pathway_ladder_for_capability(capability)
                    for capability in self.capabilities
                },
                "blocked_pathways": {
                    capability.venue.value: self._blocked_pathways_for_capability(capability)
                    for capability in self.capabilities
                },
                "promotion_rules_by_pathway": {
                    capability.venue.value: self._promotion_rules_by_pathway_for_capability(capability)
                    for capability in self.capabilities
                },
                "bootstrap_tier_b_count": len(self.bootstrap_tier_venues("tier_b")),
                "bootstrap_tier_map": bootstrap_tier_map,
                "bootstrap_role_map": bootstrap_role_map,
                "bootstrap_role_groups": {
                    role: [capability.venue.value for capability in self.capabilities if capability.bootstrap_role == role]
                    for role in sorted({capability.bootstrap_role for capability in self.capabilities if capability.bootstrap_role})
                },
                "planning_buckets": planning_bucket_map,
                "tradeability_map": self.tradeability_map(),
                "paper_execution_like_venues": [venue.value for venue in self.paper_execution_like_venues()],
                "venue_taxonomy": {
                    capability.venue.value: self._venue_taxonomy_for_capability(capability)
                    for capability in self.capabilities
                },
                "venue_types": venue_types,
                "capability_notes": {capability.venue.value: _capability_notes(capability) for capability in self.capabilities},
                "api_access": {capability.venue.value: _api_access_for_capability(capability) for capability in self.capabilities},
                "supported_order_types": {capability.venue.value: _supported_order_types_for_capability(capability) for capability in self.capabilities},
                "planned_order_types": {capability.venue.value: _planned_order_types_for_capability(capability) for capability in self.capabilities},
            },
        )

    def coverage_report(self) -> RegistryCoverageReport:
        availability_by_venue: dict[str, VenueAvailabilityReport] = {}
        metadata_gap_count = 0
        for capability in self.capabilities:
            gap_count = _capability_metadata_gap_count(capability)
            metadata_gap_count += gap_count
            expected = 11
            gap_rate = round(gap_count / expected, 3)
            readiness = self._execution_readiness_for_capability(capability, self._planning_bucket_for_capability(capability))
            execution_equivalent = self._execution_equivalent_for_capability(capability)
            execution_like = self._execution_like_for_capability(capability)
            execution_role = self._execution_role_for_capability(capability)
            execution_pathway = self._execution_pathway_for_capability(capability)
            pathway_modes = self._pathway_modes_for_capability(capability)
            highest_actionable_mode = self._highest_actionable_mode_for_capability(capability)
            required_operator_action = self._required_operator_action_for_capability(capability)
            promotion_target_pathway = self._promotion_target_pathway_for_capability(capability)
            promotion_rules = self._promotion_rules_for_capability(capability)
            pathway_ladder = self._pathway_ladder_for_capability(capability)
            blocked_pathways = self._blocked_pathways_for_capability(capability)
            promotion_rules_by_pathway = self._promotion_rules_by_pathway_for_capability(capability)
            readiness_stage = self._readiness_stage_for_capability(capability)
            next_pathway = self._next_pathway_for_capability(capability)
            next_pathway_rules = self._next_pathway_rules_for_capability(capability)
            bounded_execution_equivalent = self._bounded_execution_equivalent_for_capability(capability)
            bounded_execution_promotion_candidate = self._bounded_execution_promotion_candidate_for_capability(capability)
            stage_summary = self._stage_summary_for_capability(capability)
            execution_blocker_codes = self._execution_blocker_codes_for_capability(capability)
            availability_score = 1.0
            if self.is_read_only(capability.venue):
                availability_score -= 0.15
            if self.is_paper_capable(capability.venue):
                availability_score += 0.05
            if self.is_execution_capable(capability.venue):
                availability_score += 0.1
            availability_score -= min(0.35, gap_rate * 0.35)
            if capability.live_execution_supported:
                status = "live"
            elif capability.bounded_execution_supported or capability.market_execution_supported:
                status = "bounded_live"
            elif capability.dry_run_supported or self.is_paper_capable(capability.venue):
                status = "paper_ready"
            else:
                status = "read_only"
            availability_by_venue[capability.venue.value] = VenueAvailabilityReport(
                venue=capability.venue,
                venue_type=capability.venue_type.value if capability.venue_type else None,
                status=status,
                execution_readiness=readiness,
                execution_role=execution_role,
                execution_pathway=execution_pathway,
                read_only=self.is_read_only(capability.venue),
                paper_capable=self.is_paper_capable(capability.venue),
                execution_capable=self.is_execution_capable(capability.venue),
                execution_equivalent=execution_equivalent,
                execution_like=execution_like,
                supports_discovery=capability.supports_discovery,
                supports_orderbook=capability.supports_orderbook,
                supports_trades=capability.supports_trades,
                supports_execution=capability.supports_execution,
                supports_websocket=capability.supports_websocket,
                supports_paper_mode=capability.supports_paper_mode,
                api_access=list(capability.api_access or _api_access_for_capability(capability)),
                supported_order_types=list(capability.supported_order_types or _supported_order_types_for_capability(capability)),
                pathway_modes=list(pathway_modes),
                highest_actionable_mode=highest_actionable_mode,
                required_operator_action=required_operator_action,
                promotion_target_pathway=promotion_target_pathway,
                promotion_rules=list(promotion_rules),
                pathway_ladder=list(pathway_ladder),
                blocked_pathways=list(blocked_pathways),
                promotion_rules_by_pathway={
                    key: list(value)
                    for key, value in promotion_rules_by_pathway.items()
                },
                readiness_stage=readiness_stage,
                next_pathway=next_pathway,
                next_pathway_rules=list(next_pathway_rules),
                bounded_execution_equivalent=bounded_execution_equivalent,
                bounded_execution_promotion_candidate=bounded_execution_promotion_candidate,
                stage_summary=stage_summary,
                execution_blocker_codes=list(execution_blocker_codes),
                metadata_gap_count=gap_count,
                metadata_gap_rate=gap_rate,
                availability_score=round(max(0.0, min(1.0, availability_score)), 3),
                notes=list(capability.automation_constraints or capability.rate_limit_notes or []),
                metadata={
                "bootstrap_tier": capability.bootstrap_tier,
                    "bootstrap_role": capability.bootstrap_role,
                    "execution_role": execution_role,
                    "execution_pathway": execution_pathway,
                    "pathway_modes": list(pathway_modes),
                    "highest_actionable_mode": highest_actionable_mode,
                    "required_operator_action": required_operator_action,
                    "promotion_target_pathway": promotion_target_pathway,
                    "promotion_rules": list(promotion_rules),
                    "pathway_ladder": list(pathway_ladder),
                    "blocked_pathways": list(blocked_pathways),
                    "promotion_rules_by_pathway": {
                        key: list(value)
                        for key, value in promotion_rules_by_pathway.items()
                    },
                    "readiness_stage": readiness_stage,
                    "next_pathway": next_pathway,
                    "next_pathway_rules": list(next_pathway_rules),
                    "bounded_execution_equivalent": bounded_execution_equivalent,
                    "bounded_execution_promotion_candidate": bounded_execution_promotion_candidate,
                    "stage_summary": dict(stage_summary),
                    "execution_blocker_codes": list(execution_blocker_codes),
                    "qualified_venue_types": [role.value for role in _ordered_venue_types(capability.qualified_venue_types)],
                    "rate_limit_notes": list(capability.rate_limit_notes),
                    "automation_constraints": list(capability.automation_constraints),
                    "planned_order_types": _planned_order_types_for_capability(capability),
                },
            )
        total_venues = len(self.capabilities)
        execution_capable_count = len(self.execution_capable_venues())
        paper_capable_count = len(self.paper_capable_venues())
        read_only_count = len(self.read_only_venues())
        execution_equivalent_count = len(self.execution_equivalent_venues())
        execution_like_count = len(self.execution_like_venues())
        reference_only_count = len(self.reference_only_venues())
        watchlist_only_count = len(self.watchlist_only_venues())
        execution_pathway_counts = {
            pathway: sum(1 for report in availability_by_venue.values() if report.execution_pathway == pathway)
            for pathway in sorted({report.execution_pathway for report in availability_by_venue.values()})
        }
        degraded_venue_count = sum(1 for report in availability_by_venue.values() if report.availability_score < 1.0)
        return RegistryCoverageReport(
            venue_count=total_venues,
            execution_capable_count=execution_capable_count,
            paper_capable_count=paper_capable_count,
            read_only_count=read_only_count,
            degraded_venue_count=degraded_venue_count,
            degraded_venue_rate=round(degraded_venue_count / max(1, total_venues), 3),
            execution_equivalent_count=execution_equivalent_count,
            execution_like_count=execution_like_count,
            reference_only_count=reference_only_count,
            watchlist_only_count=watchlist_only_count,
            execution_pathway_counts=execution_pathway_counts,
            metadata_gap_count=metadata_gap_count,
            metadata_gap_rate=round(metadata_gap_count / max(1, total_venues * 11), 3),
            execution_surface_rate=round(execution_capable_count / max(1, total_venues), 3),
            availability_by_venue=availability_by_venue,
            role_counts={
                "execution": execution_capable_count,
                "reference": reference_only_count,
                "signal": len(self.signal_venues()),
                "watchlist": watchlist_only_count,
            },
            execution_venues=self.execution_venues(),
            paper_capable_venues=self.paper_capable_venues(),
            read_only_venues=self.read_only_venues(),
            metadata={
                "venue_count": total_venues,
                "execution_equivalent_count": execution_equivalent_count,
                "execution_like_count": execution_like_count,
                "reference_only_count": reference_only_count,
                "watchlist_only_count": watchlist_only_count,
                "execution_pathway_counts": execution_pathway_counts,
                "readiness_stage_counts": {
                    stage: sum(1 for report in availability_by_venue.values() if report.readiness_stage == stage)
                    for stage in sorted({report.readiness_stage for report in availability_by_venue.values()})
                },
                "credential_gate_counts": {
                    gate: sum(
                        1
                        for report in availability_by_venue.values()
                        if report.stage_summary.get("credential_gate") == gate
                    )
                    for gate in sorted({
                        report.stage_summary.get("credential_gate")
                        for report in availability_by_venue.values()
                    })
                },
                "api_gate_counts": {
                    gate: sum(
                        1
                        for report in availability_by_venue.values()
                        if report.stage_summary.get("api_gate") == gate
                    )
                    for gate in sorted({
                        report.stage_summary.get("api_gate")
                        for report in availability_by_venue.values()
                    })
                },
                "missing_requirement_count_by_venue": {
                    venue: len(report.stage_summary.get("missing_requirement_codes", []))
                    for venue, report in sorted(availability_by_venue.items())
                },
                "required_operator_action_counts": {
                    action: sum(1 for report in availability_by_venue.values() if report.required_operator_action == action)
                    for action in sorted({report.required_operator_action for report in availability_by_venue.values()})
                },
                "promotion_target_pathway": {
                    venue: report.promotion_target_pathway
                    for venue, report in sorted(availability_by_venue.items())
                },
                "promotion_rules": {
                    venue: list(report.promotion_rules)
                    for venue, report in sorted(availability_by_venue.items())
                },
                "pathway_ladder": {
                    venue: list(report.pathway_ladder)
                    for venue, report in sorted(availability_by_venue.items())
                },
                "blocked_pathways": {
                    venue: list(report.blocked_pathways)
                    for venue, report in sorted(availability_by_venue.items())
                },
                "promotion_rules_by_pathway": {
                    venue: {
                        key: list(value)
                        for key, value in report.promotion_rules_by_pathway.items()
                    }
                    for venue, report in sorted(availability_by_venue.items())
                },
                "degraded_venue_count": degraded_venue_count,
                "degraded_venue_rate": round(degraded_venue_count / max(1, total_venues), 3),
            },
        )

    @staticmethod
    def _planning_bucket_for_capability(capability: VenueExecutionCapability) -> str:
        if capability.qualifies_for(VenueType.execution) or capability.live_execution_supported or capability.bounded_execution_supported or capability.market_execution_supported:
            return "execution-equivalent"
        if capability.qualifies_for(VenueType.reference):
            return "reference-only"
        return "watchlist"

    @staticmethod
    def _execution_readiness_for_capability(capability: VenueExecutionCapability, planning_bucket: str) -> str:
        if capability.live_execution_supported:
            return "execution_ready"
        if capability.bounded_execution_supported or capability.market_execution_supported:
            return "execution_equivalent"
        if VenueExecutionRegistry._execution_bindable_for_capability(capability):
            return "bindable_ready"
        if planning_bucket == "execution-equivalent" and capability.bootstrap_tier == "tier_b":
            return "execution_bindable" if capability.dry_run_supported or capability.supports_paper_mode else "execution_like"
        if planning_bucket == "reference-only":
            return "reference_only"
        if planning_bucket == "watchlist":
            return "watchlist_only"
        return "read_only"

    @staticmethod
    def _execution_equivalent_for_capability(capability: VenueExecutionCapability) -> bool:
        return bool(
            capability.live_execution_supported
            or capability.bounded_execution_supported
            or capability.market_execution_supported
        )

    @staticmethod
    def _execution_bindable_for_capability(capability: VenueExecutionCapability) -> bool:
        planning_bucket = VenueExecutionRegistry._planning_bucket_for_capability(capability)
        planned_order_types = _planned_order_types_for_capability(capability)
        return bool(
            planning_bucket == "execution-equivalent"
            and not VenueExecutionRegistry._execution_equivalent_for_capability(capability)
            and capability.route_supported
            and capability.dry_run_supported
            and planned_order_types
        )

    @staticmethod
    def _execution_like_for_capability(capability: VenueExecutionCapability) -> bool:
        return (
            VenueExecutionRegistry._planning_bucket_for_capability(capability) == "execution-equivalent"
            and not VenueExecutionRegistry._execution_equivalent_for_capability(capability)
            and not VenueExecutionRegistry._execution_bindable_for_capability(capability)
        )

    @staticmethod
    def _execution_role_for_capability(capability: VenueExecutionCapability) -> str:
        if VenueExecutionRegistry._execution_equivalent_for_capability(capability):
            return "execution_equivalent"
        if VenueExecutionRegistry._execution_bindable_for_capability(capability):
            return "execution_bindable"
        if VenueExecutionRegistry._execution_like_for_capability(capability):
            return "execution_like"
        planning_bucket = VenueExecutionRegistry._planning_bucket_for_capability(capability)
        if planning_bucket == "reference-only":
            return "reference_only"
        venue_type = capability.venue_type.value if capability.venue_type is not None else capability.metadata.get("venue_type")
        if venue_type == VenueType.signal.value:
            return "signal_only"
        if venue_type == VenueType.watchlist.value:
            return "watchlist_only"
        return "read_only"

    @staticmethod
    def _execution_pathway_for_capability(capability: VenueExecutionCapability) -> str:
        if capability.live_execution_supported:
            return "live_execution"
        if capability.bounded_execution_supported or capability.market_execution_supported:
            return "bounded_execution"
        if VenueExecutionRegistry._execution_bindable_for_capability(capability):
            return "execution_bindable_dry_run"
        if VenueExecutionRegistry._execution_like_for_capability(capability):
            if capability.dry_run_supported or capability.supports_paper_mode or capability.route_supported:
                return "execution_like_dry_run"
            return "execution_like_paper_only"
        planning_bucket = VenueExecutionRegistry._planning_bucket_for_capability(capability)
        if planning_bucket == "reference-only":
            return "reference_read_only"
        venue_type = capability.venue_type.value if capability.venue_type is not None else capability.metadata.get("venue_type")
        if venue_type == VenueType.signal.value:
            return "signal_read_only"
        if venue_type == VenueType.watchlist.value:
            return "watchlist_read_only"
        if capability.dry_run_supported or capability.supports_paper_mode:
            return "dry_run_only"
        return "read_only"

    @staticmethod
    def _pathway_modes_for_capability(capability: VenueExecutionCapability) -> list[str]:
        modes: list[str] = []
        if capability.bootstrap_tier == "tier_b" and (capability.supports_paper_mode or capability.dry_run_supported):
            modes.append("paper")
        if VenueExecutionRegistry._execution_bindable_for_capability(capability) or capability.dry_run_supported:
            modes.append("dry_run")
        if capability.bounded_execution_supported or capability.market_execution_supported:
            modes.append("bounded_live")
        if capability.live_execution_supported:
            modes.append("live")
        return list(dict.fromkeys(modes))

    @staticmethod
    def _highest_actionable_mode_for_capability(capability: VenueExecutionCapability) -> str | None:
        modes = VenueExecutionRegistry._pathway_modes_for_capability(capability)
        return modes[-1] if modes else None

    @staticmethod
    def _readiness_stage_for_capability(capability: VenueExecutionCapability) -> str:
        highest_mode = VenueExecutionRegistry._highest_actionable_mode_for_capability(capability)
        if highest_mode == "live":
            return "live_ready"
        if highest_mode == "bounded_live":
            return "bounded_ready"
        if highest_mode == "dry_run":
            return "bindable_ready" if VenueExecutionRegistry._execution_bindable_for_capability(capability) else "dry_run_ready"
        if highest_mode == "paper":
            return "paper_ready"
        return "read_only"

    @staticmethod
    def _required_operator_action_for_capability(capability: VenueExecutionCapability) -> str:
        pathway = VenueExecutionRegistry._execution_pathway_for_capability(capability)
        if pathway == "live_execution":
            return "route_live_orders"
        if pathway == "bounded_execution":
            return "route_bounded_orders"
        if pathway == "execution_bindable_dry_run":
            return "run_dry_run_adapter"
        if pathway == "execution_like_dry_run":
            return "run_dry_run_adapter"
        if pathway == "execution_like_paper_only":
            return "paper_trade_only"
        if pathway == "reference_read_only":
            return "consume_reference_only"
        if pathway == "signal_read_only":
            return "consume_signal_only"
        if pathway == "watchlist_read_only":
            return "monitor_watchlist_only"
        if pathway == "dry_run_only":
            return "run_dry_run_adapter"
        return "no_order_routing"

    @staticmethod
    def _promotion_target_pathway_for_capability(capability: VenueExecutionCapability) -> str | None:
        pathway = VenueExecutionRegistry._execution_pathway_for_capability(capability)
        if pathway in {"execution_bindable_dry_run", "execution_like_dry_run", "execution_like_paper_only", "dry_run_only"}:
            return "bounded_execution"
        if pathway == "bounded_execution":
            return "live_execution"
        return None

    @staticmethod
    def _promotion_rules_for_capability(capability: VenueExecutionCapability) -> list[str]:
        target = VenueExecutionRegistry._promotion_target_pathway_for_capability(capability)
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

    @staticmethod
    def _pathway_ladder_for_capability(capability: VenueExecutionCapability) -> list[str]:
        pathway = VenueExecutionRegistry._execution_pathway_for_capability(capability)
        if pathway == "live_execution":
            return ["live_execution"]
        if pathway == "bounded_execution":
            return ["bounded_execution", "live_execution"]
        if pathway == "execution_bindable_dry_run":
            return ["execution_bindable_dry_run", "bounded_execution", "live_execution"]
        if pathway in {"execution_like_dry_run", "dry_run_only"}:
            return ["execution_bindable_dry_run", "bounded_execution", "live_execution"]
        if pathway == "execution_like_paper_only":
            return ["execution_like_paper_only", "execution_bindable_dry_run", "bounded_execution", "live_execution"]
        return [pathway]

    @staticmethod
    def _blocked_pathways_for_capability(capability: VenueExecutionCapability) -> list[str]:
        ladder = VenueExecutionRegistry._pathway_ladder_for_capability(capability)
        return ladder[1:]

    @staticmethod
    def _next_pathway_for_capability(capability: VenueExecutionCapability) -> str | None:
        blocked = VenueExecutionRegistry._blocked_pathways_for_capability(capability)
        return blocked[0] if blocked else None

    @staticmethod
    def _next_pathway_rules_for_capability(capability: VenueExecutionCapability) -> list[str]:
        next_pathway = VenueExecutionRegistry._next_pathway_for_capability(capability)
        if not next_pathway:
            return []
        return list(VenueExecutionRegistry._promotion_rules_by_pathway_for_capability(capability).get(next_pathway, []))

    @staticmethod
    def _bounded_execution_equivalent_for_capability(capability: VenueExecutionCapability) -> bool:
        return VenueExecutionRegistry._execution_pathway_for_capability(capability) in {"bounded_execution", "live_execution"}

    @staticmethod
    def _bounded_execution_promotion_candidate_for_capability(capability: VenueExecutionCapability) -> bool:
        return (
            not VenueExecutionRegistry._bounded_execution_equivalent_for_capability(capability)
            and "bounded_execution" in VenueExecutionRegistry._blocked_pathways_for_capability(capability)
        )

    @staticmethod
    def _promotion_rules_by_pathway_for_capability(capability: VenueExecutionCapability) -> dict[str, list[str]]:
        rules_by_pathway: dict[str, list[str]] = {}
        for pathway in VenueExecutionRegistry._blocked_pathways_for_capability(capability):
            if pathway == "execution_bindable_dry_run":
                rules_by_pathway[pathway] = [
                    "prove_dry_run_submit_path",
                    "prove_order_ack_path",
                    "prove_supported_order_types",
                ]
            elif pathway == "execution_like_dry_run":
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

    @staticmethod
    def _manual_execution_contract_for_capability(capability: VenueExecutionCapability) -> dict[str, Any]:
        return _manual_execution_contract_for_capability(capability)

    @staticmethod
    def _credential_gate_for_capability(capability: VenueExecutionCapability) -> str:
        pathway = VenueExecutionRegistry._execution_pathway_for_capability(capability)
        if pathway == "live_execution":
            return "live_credentials_required"
        if pathway == "bounded_execution":
            return "bounded_credentials_required"
        if pathway in {"execution_bindable_dry_run", "execution_like_dry_run", "dry_run_only"}:
            return "not_required_current_mode"
        if pathway == "execution_like_paper_only":
            return "paper_only_mode"
        return "read_only"

    @staticmethod
    def _api_gate_for_capability(capability: VenueExecutionCapability) -> str:
        api_access = set(capability.api_access or _api_access_for_capability(capability))
        pathway = VenueExecutionRegistry._execution_pathway_for_capability(capability)
        if pathway in {"live_execution", "bounded_execution"}:
            return "order_api_available" if "orders" in api_access else "order_api_missing"
        if pathway in {"execution_bindable_dry_run", "execution_like_dry_run", "dry_run_only"}:
            return "dry_run_order_api_available" if capability.route_supported and capability.dry_run_supported else "dry_run_order_api_missing"
        if pathway == "execution_like_paper_only":
            return "planning_only_no_order_api"
        if pathway == "reference_read_only":
            return "reference_only_surface"
        if pathway == "signal_read_only":
            return "signal_only_surface"
        return "watchlist_only_surface"

    @staticmethod
    def _adapter_readiness_for_capability(capability: VenueExecutionCapability) -> dict[str, bool]:
        return {
            "paper_mode_ready": capability.supports_paper_mode,
            "dry_run_adapter_ready": VenueExecutionRegistry._execution_bindable_for_capability(capability) or (capability.route_supported and capability.dry_run_supported),
            "bounded_execution_adapter_ready": bool(capability.bounded_execution_supported or capability.market_execution_supported),
            "live_execution_adapter_ready": capability.live_execution_supported,
            "cancel_path_ready": bool(capability.cancel_order_path),
            "fill_audit_ready": capability.fill_audit_supported,
            "order_audit_ready": capability.order_audit_supported,
            "position_audit_ready": capability.position_audit_supported,
        }

    @staticmethod
    def _execution_requirement_codes_for_capability(capability: VenueExecutionCapability) -> list[str]:
        pathway = VenueExecutionRegistry._execution_pathway_for_capability(capability)
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
                "credentials",
            ]
        if pathway == "execution_bindable_dry_run":
            return [
                "dry_run_adapter",
                "dry_run_order_ack",
                "planned_order_types",
            ]
        if pathway in {"execution_like_dry_run", "dry_run_only"}:
            return [
                "dry_run_adapter",
                "supported_order_types",
                "order_ack_path",
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

    @staticmethod
    def _missing_requirement_codes_for_capability(capability: VenueExecutionCapability) -> list[str]:
        blocker_map = {
            "execution_like_paper_only": "dry_run_adapter",
            "bootstrap_execution_bindable": "dry_run_adapter",
            "execution_unsupported": "execution_api",
            "no_live_execution_adapter": "live_execution_adapter",
            "no_bounded_execution_adapter": "bounded_execution_adapter",
            "planned_order_types_only": "supported_order_types",
            "no_live_websocket": "market_feed_api",
            "no_trade_surface": "trade_surface",
            "reference_only": "reference_surface",
            "signal_only": "signal_surface",
            "watchlist_only": "watchlist_surface",
        }
        missing = [
            blocker_map[code]
            for code in VenueExecutionRegistry._execution_blocker_codes_for_capability(capability)
            if code in blocker_map
        ]
        return list(dict.fromkeys(missing))

    @staticmethod
    def _operator_checklist_for_capability(capability: VenueExecutionCapability) -> list[str]:
        checklist = [f"action:{VenueExecutionRegistry._required_operator_action_for_capability(capability)}"]
        checklist.extend(
            f"gate:{code}" for code in VenueExecutionRegistry._missing_requirement_codes_for_capability(capability)
        )
        checklist.extend(
            f"promote:{rule}" for rule in VenueExecutionRegistry._next_pathway_rules_for_capability(capability)
        )
        credential_gate = VenueExecutionRegistry._credential_gate_for_capability(capability)
        if credential_gate not in {"not_required_current_mode", "paper_only_mode"}:
            checklist.append(f"credentials:{credential_gate}")
        checklist.append(f"api:{VenueExecutionRegistry._api_gate_for_capability(capability)}")
        return list(dict.fromkeys(checklist))

    @staticmethod
    def _promotion_evidence_by_pathway_for_capability(capability: VenueExecutionCapability) -> dict[str, dict[str, Any]]:
        evidence: dict[str, dict[str, Any]] = {}
        current_pathway = VenueExecutionRegistry._execution_pathway_for_capability(capability)
        rules_by_pathway = VenueExecutionRegistry._promotion_rules_by_pathway_for_capability(capability)
        for pathway in VenueExecutionRegistry._pathway_ladder_for_capability(capability):
            required_rules = list(rules_by_pathway.get(pathway, []))
            status = "current" if pathway == current_pathway else "blocked"
            evidence[pathway] = {
                "status": status,
                "required_evidence": required_rules,
                "missing_evidence": list(required_rules if status == "blocked" else []),
                "evidence_count": len(required_rules),
            }
        return evidence

    @staticmethod
    def _stage_summary_for_capability(capability: VenueExecutionCapability) -> dict[str, Any]:
        execution_pathway = VenueExecutionRegistry._execution_pathway_for_capability(capability)
        pathway_ladder = VenueExecutionRegistry._pathway_ladder_for_capability(capability)
        blocked_pathways = VenueExecutionRegistry._blocked_pathways_for_capability(capability)
        next_pathway = VenueExecutionRegistry._next_pathway_for_capability(capability)
        next_pathway_rules = VenueExecutionRegistry._next_pathway_rules_for_capability(capability)
        adapter_readiness = VenueExecutionRegistry._adapter_readiness_for_capability(capability)
        execution_requirement_codes = VenueExecutionRegistry._execution_requirement_codes_for_capability(capability)
        missing_requirement_codes = VenueExecutionRegistry._missing_requirement_codes_for_capability(capability)
        manual_execution_contract = VenueExecutionRegistry._manual_execution_contract_for_capability(capability)
        promotion_ladder = manual_execution_contract.get("promotion_steps", [])
        pathway_summary = VenueExecutionRegistry._pathway_summary_for_capability(capability)
        operator_summary = VenueExecutionRegistry._operator_summary_for_capability(capability)
        promotion_summary = VenueExecutionRegistry._promotion_summary_for_capability(capability)
        blocker_summary = VenueExecutionRegistry._blocker_summary_for_capability(capability)
        return {
            "execution_pathway": execution_pathway,
            "current_pathway": execution_pathway,
            "readiness_stage": VenueExecutionRegistry._readiness_stage_for_capability(capability),
            "highest_actionable_mode": VenueExecutionRegistry._highest_actionable_mode_for_capability(capability),
            "pathway_summary": pathway_summary,
            "operator_summary": operator_summary,
            "promotion_summary": promotion_summary,
            "blocker_summary": blocker_summary,
            "required_operator_action": VenueExecutionRegistry._required_operator_action_for_capability(capability),
            "credential_gate": VenueExecutionRegistry._credential_gate_for_capability(capability),
            "api_gate": VenueExecutionRegistry._api_gate_for_capability(capability),
            "adapter_readiness": adapter_readiness,
            "execution_requirement_codes": execution_requirement_codes,
            "missing_requirement_codes": missing_requirement_codes,
            "missing_requirement_count": len(missing_requirement_codes),
            "operator_checklist": VenueExecutionRegistry._operator_checklist_for_capability(capability),
            "next_pathway": next_pathway,
            "next_pathway_rules": next_pathway_rules,
            "next_pathway_rule_count": len(next_pathway_rules),
            "promotion_evidence_by_pathway": VenueExecutionRegistry._promotion_evidence_by_pathway_for_capability(capability),
            "bounded_execution_equivalent": VenueExecutionRegistry._bounded_execution_equivalent_for_capability(capability),
            "bounded_execution_promotion_candidate": VenueExecutionRegistry._bounded_execution_promotion_candidate_for_capability(capability),
            "operator_ready_now": VenueExecutionRegistry._highest_actionable_mode_for_capability(capability) is not None,
            "pathway_ladder": pathway_ladder,
            "pathway_count": len(pathway_ladder),
            "blocked_pathways": blocked_pathways,
            "blocked_pathway_count": len(blocked_pathways),
            "remaining_pathways": blocked_pathways,
            "remaining_pathway_count": len(blocked_pathways),
            "manual_execution_contract": dict(manual_execution_contract),
            "promotion_ladder": [dict(step) for step in promotion_ladder],
        }

    @staticmethod
    def _pathway_summary_for_capability(capability: VenueExecutionCapability) -> str:
        pathway = VenueExecutionRegistry._execution_pathway_for_capability(capability)
        next_pathway = VenueExecutionRegistry._next_pathway_for_capability(capability) or "none"
        blocked = VenueExecutionRegistry._blocked_pathways_for_capability(capability)
        return f"pathway={pathway} | readiness={VenueExecutionRegistry._readiness_stage_for_capability(capability)} | next={next_pathway} | blocked={','.join(blocked) if blocked else 'none'}"

    @staticmethod
    def _operator_summary_for_capability(capability: VenueExecutionCapability) -> str:
        action = VenueExecutionRegistry._required_operator_action_for_capability(capability)
        credential_gate = VenueExecutionRegistry._credential_gate_for_capability(capability)
        api_gate = VenueExecutionRegistry._api_gate_for_capability(capability)
        return f"action={action} | credentials={credential_gate} | api={api_gate}"

    @staticmethod
    def _promotion_summary_for_capability(capability: VenueExecutionCapability) -> str:
        target = VenueExecutionRegistry._promotion_target_pathway_for_capability(capability) or "none"
        rules = VenueExecutionRegistry._promotion_rules_for_capability(capability)
        current_mode = VenueExecutionRegistry._highest_actionable_mode_for_capability(capability) or "none"
        return f"promote->{target} | rules={len(rules)} | current_mode={current_mode}"

    @staticmethod
    def _blocker_summary_for_capability(capability: VenueExecutionCapability) -> str:
        blockers = VenueExecutionRegistry._execution_blocker_codes_for_capability(capability)
        return ", ".join(blockers) if blockers else "none"

    @staticmethod
    def _execution_blocker_codes_for_capability(capability: VenueExecutionCapability) -> list[str]:
        pathway = VenueExecutionRegistry._execution_pathway_for_capability(capability)
        blockers: list[str] = []
        if not capability.supports_execution:
            blockers.append("execution_unsupported")
        if pathway == "bounded_execution":
            blockers.append("no_live_execution_adapter")
        elif pathway in {"execution_bindable_dry_run", "execution_like_dry_run", "execution_like_paper_only"}:
            blockers.append("execution_bindable_only")
            blockers.append("no_live_execution_adapter")
            if not (capability.bounded_execution_supported or capability.market_execution_supported):
                blockers.append("no_bounded_execution_adapter")
        elif pathway == "reference_read_only":
            blockers.append("reference_only")
        elif pathway == "signal_read_only":
            blockers.append("signal_only")
        elif pathway == "watchlist_read_only":
            blockers.append("watchlist_only")
        elif pathway == "read_only":
            blockers.append("read_only_surface")
        planned_order_types = _planned_order_types_for_capability(capability)
        supported_order_types = _supported_order_types_for_capability(capability)
        if planned_order_types and not supported_order_types and pathway != "execution_bindable_dry_run":
            blockers.append("planned_order_types_only")
        if pathway in {"live_execution", "bounded_execution", "execution_bindable_dry_run", "execution_like_dry_run", "execution_like_paper_only"} and not capability.supports_trades:
            blockers.append("no_trade_surface")
        return list(dict.fromkeys(blockers))

    @staticmethod
    def _tradeability_class_for_capability(capability: VenueExecutionCapability) -> str:
        venue_type = capability.venue_type.value if capability.venue_type is not None else capability.metadata.get("venue_type")
        planning_bucket = VenueExecutionRegistry._planning_bucket_for_capability(capability)
        if capability.live_execution_supported:
            return "live_execution"
        if capability.bounded_execution_supported or capability.market_execution_supported:
            return "bounded_execution"
        if VenueExecutionRegistry._execution_bindable_for_capability(capability):
            return "execution_bindable_dry_run"
        if planning_bucket == "execution-equivalent" and (capability.dry_run_supported or capability.supports_paper_mode):
            return "execution_like_paper_only"
        if planning_bucket == "reference-only" and (capability.dry_run_supported or capability.supports_paper_mode):
            return "reference_paper_only"
        if venue_type == VenueType.signal.value and (capability.dry_run_supported or capability.supports_paper_mode):
            return "signal_paper_only"
        if venue_type == VenueType.watchlist.value and (capability.dry_run_supported or capability.supports_paper_mode):
            return "watchlist_paper_only"
        if planning_bucket == "reference-only":
            return "reference_only"
        if venue_type == VenueType.signal.value:
            return "signal_only"
        if venue_type == VenueType.watchlist.value:
            return "watchlist_only"
        return "read_only"

    @staticmethod
    def _venue_taxonomy_for_capability(capability: VenueExecutionCapability) -> str | None:
        explicit = capability.metadata.get("venue_taxonomy")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()
        if capability.bootstrap_tier == "tier_b" and capability.bootstrap_role:
            return capability.bootstrap_role
        venue_kind = capability.metadata.get("venue_kind")
        if isinstance(venue_kind, str) and venue_kind.strip():
            return venue_kind.strip()
        if capability.venue_type is not None:
            return capability.venue_type.value
        return None

    @staticmethod
    def _execution_taxonomy_for_capability(capability: VenueExecutionCapability) -> str:
        explicit = capability.metadata.get("execution_taxonomy")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()
        if capability.live_execution_supported:
            return "execution_ready"
        if capability.bounded_execution_supported or capability.market_execution_supported:
            return "execution_equivalent"
        if VenueExecutionRegistry._execution_bindable_for_capability(capability):
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


def _planning_bucket_for_capability(capability: VenueExecutionCapability) -> str:
    if capability.qualifies_for(VenueType.execution) or capability.live_execution_supported or capability.bounded_execution_supported or capability.market_execution_supported:
        return "execution-equivalent"
    if capability.qualifies_for(VenueType.reference):
        return "reference-only"
    return "watchlist"


def _api_access_for_capability(capability: VenueExecutionCapability) -> list[str]:
    if not (capability.route_supported or capability.dry_run_supported or capability.live_execution_supported or capability.bounded_execution_supported or capability.market_execution_supported):
        return []
    read_access = ["catalog", "snapshot", "events", "evidence"]
    if capability.route_supported or capability.dry_run_supported:
        read_access.extend(["orderbook", "trades", "positions"])
    if capability.live_execution_supported or capability.bounded_execution_supported or capability.market_execution_supported:
        read_access.extend(["orders", "cancel"])
    return list(dict.fromkeys(read_access))


def _supported_order_types_for_capability(capability: VenueExecutionCapability) -> list[str]:
    if capability.live_execution_supported or capability.bounded_execution_supported or capability.market_execution_supported:
        return ["limit"]
    return []


def _planned_order_types_for_capability(capability: VenueExecutionCapability) -> list[str]:
    explicit = capability.metadata.get("planned_order_types")
    if isinstance(explicit, list) and explicit:
        return [str(item) for item in explicit if str(item).strip()]
    if capability.live_execution_supported or capability.bounded_execution_supported or capability.market_execution_supported:
        return list(capability.supported_order_types or ["limit"])
    if VenueExecutionRegistry._execution_like_for_capability(capability):
        return ["limit"]
    return []


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


def _manual_execution_contract_for_capability(capability: VenueExecutionCapability) -> dict[str, Any]:
    pathway = VenueExecutionRegistry._execution_pathway_for_capability(capability)
    promotion_target_pathway = VenueExecutionRegistry._promotion_target_pathway_for_capability(capability)
    promotion_rules_by_pathway = VenueExecutionRegistry._promotion_rules_by_pathway_for_capability(capability)
    blocked_pathways = VenueExecutionRegistry._blocked_pathways_for_capability(capability)
    next_pathway = VenueExecutionRegistry._next_pathway_for_capability(capability)
    next_pathway_rules = VenueExecutionRegistry._next_pathway_rules_for_capability(capability)
    ladder = VenueExecutionRegistry._pathway_ladder_for_capability(capability)
    return {
        "current_pathway": pathway,
        "manual_execution_mode": _manual_execution_mode_for_pathway(pathway),
        "operator_action": VenueExecutionRegistry._required_operator_action_for_capability(capability),
        "manual_route_kind": _manual_execution_mode_for_pathway(pathway),
        "allows_dry_run_routing": pathway in {"execution_bindable_dry_run", "execution_like_dry_run", "dry_run_only"},
        "allows_bounded_order_routing": pathway == "bounded_execution",
        "allows_live_order_routing": pathway == "live_execution",
        "requires_promotion": pathway in {"execution_bindable_dry_run", "execution_like_dry_run", "execution_like_paper_only", "dry_run_only"},
        "promotion_target_pathway": promotion_target_pathway,
        "promotion_rules_by_pathway": {key: list(value) for key, value in promotion_rules_by_pathway.items()},
        "next_pathway": next_pathway,
        "next_pathway_rules": list(next_pathway_rules),
        "pathway_ladder": list(ladder),
        "blocked_pathways": list(blocked_pathways),
        "promotion_steps": [
            _promotion_ladder_step(
                pathway=step_pathway,
                current_pathway=pathway,
                promotion_target_pathway=promotion_target_pathway,
                promotion_rules_by_pathway=promotion_rules_by_pathway,
                next_pathway_rules=next_pathway_rules,
                blocked_pathways=blocked_pathways,
            )
            for step_pathway in ladder
        ],
    }


def _capability_notes(capability: VenueExecutionCapability) -> dict[str, Any]:
    return {
        "venue_type": capability.venue_type.value if capability.venue_type else None,
        "role_labels": [role.value for role in _ordered_venue_types(capability.qualified_venue_types)],
        "api_access": _api_access_for_capability(capability),
        "supported_order_types": _supported_order_types_for_capability(capability),
        "planned_order_types": _planned_order_types_for_capability(capability),
        "discovery_notes": list(capability.discovery_notes),
        "orderbook_notes": list(capability.orderbook_notes),
        "trades_notes": list(capability.trades_notes),
        "execution_notes": list(capability.execution_notes),
        "websocket_notes": list(capability.websocket_notes),
        "paper_notes": list(capability.paper_notes),
        "automation_constraints": list(capability.automation_constraints),
        "rate_limit_notes": list(capability.rate_limit_notes),
        "tos_notes": list(capability.tos_notes),
        "allowed_jurisdictions": sorted(capability.allowed_jurisdictions),
        "allowed_account_types": sorted(capability.allowed_account_types),
        "automation_allowed": capability.automation_allowed,
        "dry_run_requires_authorization": capability.dry_run_requires_authorization,
        "dry_run_requires_compliance": capability.dry_run_requires_compliance,
        "live_requires_authorization": capability.live_requires_authorization,
        "live_requires_compliance": capability.live_requires_compliance,
        "live_order_path": capability.live_order_path,
        "bounded_order_path": capability.bounded_order_path,
        "cancel_order_path": capability.cancel_order_path,
    }


def _capability_metadata_gap_count(capability: VenueExecutionCapability) -> int:
    gap_fields = [
        capability.api_access,
        capability.supported_order_types,
        capability.rate_limit_notes,
        capability.automation_constraints,
        capability.tos_notes,
        capability.discovery_notes,
        capability.orderbook_notes,
        capability.trades_notes,
        capability.execution_notes,
        capability.websocket_notes,
        capability.paper_notes,
    ]
    return sum(1 for field in gap_fields if not field)


def _capability(
    *,
    venue: VenueName,
    adapter_name: str,
    venue_type: VenueType | None = None,
    bootstrap_tier: str | None = None,
    bootstrap_role: str | None = None,
    route_supported: bool,
    dry_run_supported: bool,
    live_execution_supported: bool,
    bounded_execution_supported: bool,
    market_execution_supported: bool,
    api_access: list[str] | None = None,
    supported_order_types: list[str] | None = None,
    live_order_path: str | None = None,
    bounded_order_path: str | None = None,
    cancel_order_path: str | None = None,
    supports_discovery: bool | None = None,
    supports_orderbook: bool | None = None,
    supports_trades: bool | None = None,
    supports_execution: bool | None = None,
    supports_websocket: bool | None = None,
    supports_paper_mode: bool | None = None,
    qualified_venue_types: set[VenueType],
    backend_mode: str,
    venue_kind: str,
    allowed_jurisdictions: set[str] | None = None,
    allowed_account_types: set[str] | None = None,
    automation_allowed: bool = True,
    rate_limit_notes: list[str] | None = None,
    tos_notes: list[str] | None = None,
    discovery_notes: list[str] | None = None,
    orderbook_notes: list[str] | None = None,
    trades_notes: list[str] | None = None,
    execution_notes: list[str] | None = None,
    websocket_notes: list[str] | None = None,
    paper_notes: list[str] | None = None,
    automation_constraints: list[str] | None = None,
    dry_run_requires_authorization: bool = False,
    dry_run_requires_compliance: bool = False,
    live_requires_authorization: bool = True,
    live_requires_compliance: bool = True,
    metadata: dict[str, Any] | None = None,
) -> VenueExecutionCapability:
    derived_supports_execution = supports_execution if supports_execution is not None else bool(
        live_execution_supported or bounded_execution_supported or market_execution_supported
    )
    derived_supports_paper_mode = supports_paper_mode if supports_paper_mode is not None else bool(
        dry_run_supported or bounded_execution_supported or market_execution_supported
    )
    derived_supports_discovery = supports_discovery if supports_discovery is not None else bool(
        route_supported or dry_run_supported or live_execution_supported or bounded_execution_supported or market_execution_supported or discovery_notes
    )
    derived_supports_orderbook = supports_orderbook if supports_orderbook is not None else bool(
        route_supported or dry_run_supported or live_execution_supported or bounded_execution_supported or market_execution_supported
    )
    derived_supports_trades = supports_trades if supports_trades is not None else bool(
        route_supported or dry_run_supported or live_execution_supported or bounded_execution_supported or market_execution_supported
    )
    derived_supports_websocket = supports_websocket if supports_websocket is not None else False
    return VenueExecutionCapability(
        venue=venue,
        adapter_name=adapter_name,
        venue_type=venue_type,
        bootstrap_tier=bootstrap_tier,
        bootstrap_role=bootstrap_role,
        supports_discovery=derived_supports_discovery,
        supports_orderbook=derived_supports_orderbook,
        supports_trades=derived_supports_trades,
        supports_execution=derived_supports_execution,
        supports_websocket=derived_supports_websocket,
        supports_paper_mode=derived_supports_paper_mode,
        route_supported=route_supported,
        dry_run_supported=dry_run_supported,
        live_execution_supported=live_execution_supported,
        bounded_execution_supported=bounded_execution_supported,
        market_execution_supported=market_execution_supported,
        live_order_path=live_order_path,
        bounded_order_path=bounded_order_path,
        cancel_order_path=cancel_order_path,
        qualified_venue_types=qualified_venue_types,
        dry_run_requires_authorization=dry_run_requires_authorization,
        dry_run_requires_compliance=dry_run_requires_compliance,
        live_requires_authorization=live_requires_authorization,
        live_requires_compliance=live_requires_compliance,
        allowed_jurisdictions=set(allowed_jurisdictions or set()),
        allowed_account_types=set(allowed_account_types or set()),
        automation_allowed=automation_allowed,
        rate_limit_notes=list(rate_limit_notes or []),
        tos_notes=list(tos_notes or []),
        discovery_notes=list(discovery_notes or []),
        orderbook_notes=list(orderbook_notes or []),
        trades_notes=list(trades_notes or []),
        execution_notes=list(execution_notes or []),
        websocket_notes=list(websocket_notes or []),
        paper_notes=list(paper_notes or []),
        automation_constraints=list(automation_constraints or []),
        metadata={
            **dict(metadata or {}),
            "backend_mode": backend_mode,
            "venue_kind": venue_kind,
            "venue_type": venue_type.value if venue_type else None,
            "bootstrap_tier": bootstrap_tier,
            "bootstrap_role": bootstrap_role,
            "qualified_venue_types": [role.value for role in _ordered_venue_types(qualified_venue_types)],
            "role_labels": [role.value for role in _ordered_venue_types(qualified_venue_types)],
            "supports_discovery": derived_supports_discovery,
            "supports_orderbook": derived_supports_orderbook,
            "supports_trades": derived_supports_trades,
            "supports_execution": derived_supports_execution,
            "supports_websocket": derived_supports_websocket,
            "supports_paper_mode": derived_supports_paper_mode,
            "planning_bucket": "execution-equivalent" if live_execution_supported or bounded_execution_supported or market_execution_supported or venue_type == VenueType.execution else ("reference-only" if venue_type == VenueType.reference else "watchlist"),
            "order_paths": {
                "live": live_order_path,
                "bounded": bounded_order_path,
                "cancel": cancel_order_path,
            },
            "capability_notes": {
                "discovery_notes": list(discovery_notes or []),
                "orderbook_notes": list(orderbook_notes or []),
                "trades_notes": list(trades_notes or []),
                "execution_notes": list(execution_notes or []),
                "api_access": list(api_access or []),
                "supported_order_types": list(supported_order_types or []),
                "websocket_notes": list(websocket_notes or []),
                "paper_notes": list(paper_notes or []),
                "automation_constraints": list(automation_constraints or []),
                "rate_limit_notes": list(rate_limit_notes or []),
                "tos_notes": list(tos_notes or []),
            },
            "automation_allowed": automation_allowed,
            "allowed_jurisdictions": sorted(allowed_jurisdictions or set()),
            "allowed_account_types": sorted(allowed_account_types or set()),
            "api_access": list(api_access or []),
            "supported_order_types": list(supported_order_types or []),
        },
    )


DEFAULT_VENUE_EXECUTION_REGISTRY = VenueExecutionRegistry(
    capabilities=[
        _capability(
            venue=VenueName.polymarket,
            adapter_name="polymarket_execution_adapter",
            venue_type=VenueType.execution,
            bootstrap_tier=None,
            bootstrap_role=None,
            supports_discovery=True,
            supports_orderbook=True,
            supports_trades=True,
            supports_execution=True,
            supports_websocket=False,
            supports_paper_mode=True,
            route_supported=True,
            dry_run_supported=True,
            live_execution_supported=True,
            bounded_execution_supported=True,
            market_execution_supported=True,
            api_access=["catalog", "snapshot", "orderbook", "trades", "positions", "events", "evidence", "orders", "cancel"],
            supported_order_types=["limit"],
            live_order_path="external_live_api",
            bounded_order_path="external_bounded_api",
            cancel_order_path="external_live_cancel_api",
            qualified_venue_types={VenueType.execution, VenueType.watchlist},
            backend_mode="auto",
            venue_kind="execution",
            live_requires_authorization=True,
            live_requires_compliance=True,
            discovery_notes=["Execution venue with discovery and routing enabled."],
            orderbook_notes=["Orderbook data is expected for execution planning."],
            trades_notes=["Trade history is part of execution audit and replay."],
            execution_notes=["Live execution is allowed when authorization and compliance pass."],
            websocket_notes=["Streaming is expected when the live adapter exposes feeds."],
            paper_notes=["Dry-run and bounded rehearsal are supported."],
            automation_constraints=["Authorization required for live routing.", "Compliance approval required for live routing.", "Respect venue rate limits."],
            rate_limit_notes=["Follow venue-specific rate limits and back off on feed or order traffic."],
            metadata={"planned_order_types": ["limit"]},
        ),
        _capability(
            venue=VenueName.kalshi,
            adapter_name="kalshi_execution_adapter",
            venue_type=VenueType.execution,
            bootstrap_tier=None,
            bootstrap_role=None,
            supports_discovery=True,
            supports_orderbook=True,
            supports_trades=True,
            supports_execution=True,
            supports_websocket=False,
            supports_paper_mode=True,
            route_supported=True,
            dry_run_supported=True,
            live_execution_supported=False,
            bounded_execution_supported=True,
            market_execution_supported=True,
            api_access=["catalog", "snapshot", "orderbook", "trades", "positions", "events", "evidence", "orders", "cancel"],
            supported_order_types=["limit"],
            bounded_order_path="external_bounded_api",
            cancel_order_path="external_bounded_cancel_api",
            qualified_venue_types={VenueType.execution, VenueType.watchlist},
            backend_mode="adapter-planned",
            venue_kind="execution",
            live_requires_authorization=True,
            live_requires_compliance=True,
            discovery_notes=["Execution venue with bounded routing enabled."],
            orderbook_notes=["Orderbook data is expected for bounded execution planning."],
            trades_notes=["Trade history is part of execution audit and replay."],
            execution_notes=["Bounded execution is supported; live execution is not enabled here."],
            websocket_notes=["Streaming support is adapter dependent."],
            paper_notes=["Dry-run and bounded rehearsal are supported."],
            automation_constraints=["Authorization required for bounded routing.", "Compliance approval required before live routing.", "Respect venue rate limits."],
            rate_limit_notes=["Follow venue-specific rate limits and back off on feed or order traffic."],
            metadata={"planned_order_types": ["limit"]},
        ),
        _capability(
            venue=VenueName.robinhood,
            adapter_name="robinhood_execution_adapter",
            venue_type=VenueType.execution,
            bootstrap_tier="tier_b",
            bootstrap_role="event_contract_bootstrap",
            supports_discovery=True,
            supports_orderbook=True,
            supports_trades=True,
            supports_execution=False,
            supports_websocket=False,
            supports_paper_mode=True,
            route_supported=True,
            dry_run_supported=True,
            live_execution_supported=False,
            bounded_execution_supported=False,
            market_execution_supported=False,
            api_access=["catalog", "snapshot", "orderbook", "trades", "positions", "events", "evidence"],
            supported_order_types=[],
            qualified_venue_types={VenueType.execution, VenueType.watchlist},
            backend_mode="bootstrap",
            venue_kind="execution_like",
            discovery_notes=["Execution-like bootstrap routing is available for planning."],
            orderbook_notes=["Synthetic orderbook snapshots are exposed by the bootstrap adapter."],
            trades_notes=["Synthetic trade history is exposed for paper review."],
            execution_notes=["No live order placement is permitted in bootstrap mode."],
            websocket_notes=["No live websocket is exposed in bootstrap mode."],
            paper_notes=["Paper rehearsal is supported via bootstrap descriptors."],
            automation_constraints=["Read-only bootstrap profile.", "No live automation."],
            rate_limit_notes=["Bootstrap mode does not consume live venue rate limits."],
            metadata={"planned_order_types": ["limit"], "mockable_execution_like": True},
        ),
        _capability(
            venue=VenueName.cryptocom,
            adapter_name="cryptocom_execution_adapter",
            venue_type=VenueType.execution,
            bootstrap_tier="tier_b",
            bootstrap_role="event_contract_bootstrap",
            supports_discovery=True,
            supports_orderbook=True,
            supports_trades=True,
            supports_execution=False,
            supports_websocket=False,
            supports_paper_mode=True,
            route_supported=True,
            dry_run_supported=True,
            live_execution_supported=False,
            bounded_execution_supported=False,
            market_execution_supported=False,
            api_access=["catalog", "snapshot", "orderbook", "trades", "positions", "events", "evidence"],
            supported_order_types=[],
            qualified_venue_types={VenueType.execution, VenueType.watchlist},
            backend_mode="bootstrap",
            venue_kind="execution_like",
            discovery_notes=["Execution-like bootstrap routing is available for planning."],
            orderbook_notes=["Synthetic orderbook snapshots are exposed by the bootstrap adapter."],
            trades_notes=["Synthetic trade history is exposed for paper review."],
            execution_notes=["No live order placement is permitted in bootstrap mode."],
            websocket_notes=["No live websocket is exposed in bootstrap mode."],
            paper_notes=["Paper rehearsal is supported via bootstrap descriptors."],
            automation_constraints=["Read-only bootstrap profile.", "No live automation."],
            rate_limit_notes=["Bootstrap mode does not consume live venue rate limits."],
            metadata={"planned_order_types": ["limit"], "mockable_execution_like": True},
        ),
        _capability(
            venue=VenueName.metaculus,
            adapter_name="metaculus_execution_adapter",
            venue_type=VenueType.reference,
            bootstrap_tier="tier_b",
            bootstrap_role="reference_bootstrap",
            supports_discovery=True,
            supports_orderbook=False,
            supports_trades=False,
            supports_execution=False,
            supports_websocket=False,
            supports_paper_mode=False,
            route_supported=False,
            dry_run_supported=False,
            live_execution_supported=False,
            bounded_execution_supported=False,
            market_execution_supported=False,
            api_access=["catalog", "snapshot", "events", "evidence"],
            supported_order_types=[],
            qualified_venue_types={VenueType.reference, VenueType.watchlist},
            backend_mode="bootstrap",
            venue_kind="reference",
            discovery_notes=["Reference discovery is available for research and comparison."],
            orderbook_notes=["No orderbook is exposed for reference-only venues."],
            trades_notes=["No trades are exposed for reference-only venues."],
            execution_notes=["No execution routing is permitted for reference-only venues."],
            websocket_notes=["No live websocket is exposed for reference-only venues."],
            paper_notes=["Paper planning is supported for research mirrors only."],
            automation_constraints=["Read-only reference profile.", "No live automation."],
            rate_limit_notes=["Bootstrap mode does not consume live venue rate limits."],
        ),
        _capability(
            venue=VenueName.manifold,
            adapter_name="manifold_execution_adapter",
            venue_type=VenueType.signal,
            bootstrap_tier="tier_b",
            bootstrap_role="signal_bootstrap",
            supports_discovery=True,
            supports_orderbook=False,
            supports_trades=False,
            supports_execution=False,
            supports_websocket=False,
            supports_paper_mode=False,
            route_supported=False,
            dry_run_supported=False,
            live_execution_supported=False,
            bounded_execution_supported=False,
            market_execution_supported=False,
            api_access=["catalog", "snapshot", "events", "evidence"],
            supported_order_types=[],
            qualified_venue_types={VenueType.signal, VenueType.watchlist},
            backend_mode="bootstrap",
            venue_kind="signal",
            discovery_notes=["Signal discovery is available via bootstrap descriptors."],
            orderbook_notes=["No live orderbook is exposed for signal venues."],
            trades_notes=["Synthetic trade history is surfaced for research and replay."],
            execution_notes=["No live execution is permitted for signal venues."],
            websocket_notes=["No live websocket is exposed for signal venues."],
            paper_notes=["Paper planning is supported from signal bootstrap data."],
            automation_constraints=["Read-only signal profile.", "No live order placement."],
            rate_limit_notes=["Bootstrap mode does not consume live venue rate limits."],
        ),
        _capability(
            venue=VenueName.opinion_trade,
            adapter_name="opinion_trade_execution_adapter",
            venue_type=VenueType.watchlist,
            bootstrap_tier="tier_b",
            bootstrap_role="watchlist_bootstrap",
            supports_discovery=True,
            supports_orderbook=False,
            supports_trades=False,
            supports_execution=False,
            supports_websocket=False,
            supports_paper_mode=False,
            route_supported=False,
            dry_run_supported=False,
            live_execution_supported=False,
            bounded_execution_supported=False,
            market_execution_supported=False,
            api_access=["catalog", "snapshot", "events", "evidence"],
            supported_order_types=[],
            qualified_venue_types={VenueType.signal, VenueType.watchlist},
            backend_mode="bootstrap",
            venue_kind="watchlist",
            discovery_notes=["Watchlist discovery is available via bootstrap descriptors."],
            orderbook_notes=["No live orderbook is exposed for watchlist venues."],
            trades_notes=["Synthetic trade history is surfaced for watchlist review."],
            execution_notes=["No live execution is permitted for watchlist venues."],
            websocket_notes=["No live websocket is exposed for watchlist venues."],
            paper_notes=["Paper planning is supported from watchlist bootstrap data."],
            automation_constraints=["Read-only watchlist profile.", "No live automation."],
            rate_limit_notes=["Bootstrap mode does not consume live venue rate limits."],
        ),
    ]
)

class RunRegistryEntry(BaseModel):
    run_id: str
    market_id: str
    venue: str
    manifest_path: str
    mode: str = "advise"
    created_at: str
    updated_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunRegistry(BaseModel):
    schema_version: str = "v1"
    entries: list[RunRegistryEntry] = Field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "RunRegistry":
        file_path = Path(path)
        if not file_path.exists():
            return cls()
        return cls.model_validate_json(file_path.read_text(encoding="utf-8"))

    def save(self, path: str | Path) -> Path:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.model_dump_json(indent=2)
        with tempfile.NamedTemporaryFile("w", delete=False, dir=str(file_path.parent), encoding="utf-8") as handle:
            handle.write(payload)
            tmp_path = Path(handle.name)
        tmp_path.replace(file_path)
        return file_path

    def record(self, manifest: RunManifest, *, manifest_path: str | Path) -> RunRegistryEntry:
        entry = RunRegistryEntry(
            run_id=manifest.run_id,
            market_id=manifest.market_id,
            venue=manifest.venue.value,
            manifest_path=str(manifest_path),
            mode=manifest.mode,
            created_at=manifest.created_at.isoformat(),
            updated_at=manifest.updated_at.isoformat() if manifest.updated_at else None,
            metadata=dict(manifest.metadata),
        )
        self.entries = [item for item in self.entries if item.run_id != manifest.run_id] + [entry]
        self.entries.sort(key=lambda item: item.created_at)
        return entry

    def get(self, run_id: str) -> RunRegistryEntry | None:
        for entry in self.entries:
            if entry.run_id == run_id:
                return entry
        return None

    def list_entries(self) -> list[RunRegistryEntry]:
        return list(self.entries)

    def recent(self, limit: int = 20) -> list[RunRegistryEntry]:
        return list(self.entries[-limit:])


class RunRegistryStore:
    def __init__(self, paths: PredictionMarketPaths | None = None) -> None:
        self.paths = paths or default_prediction_market_paths()
        self.paths.ensure_layout()

    def load(self) -> RunRegistry:
        return RunRegistry.load(self.paths.registry_path)

    def save(self, registry: RunRegistry) -> Path:
        return registry.save(self.paths.registry_path)

    def record_manifest(self, manifest: RunManifest, *, manifest_path: str | Path) -> RunRegistryEntry:
        registry = self.load()
        entry = registry.record(manifest, manifest_path=manifest_path)
        self.save(registry)
        return entry

    def get_manifest(self, run_id: str) -> RunManifest:
        manifest_path = self.paths.run_manifest_path(run_id)
        return RunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))

    def list_manifests(self) -> list[RunManifest]:
        registry = self.load()
        manifests: list[RunManifest] = []
        for entry in registry.entries:
            manifest_path = Path(entry.manifest_path)
            if manifest_path.exists():
                manifests.append(RunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8")))
        return manifests
