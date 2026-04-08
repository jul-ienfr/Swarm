from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .models import MarketDescriptor, MarketSnapshot, MarketStatus, ResolutionPolicy, ResolutionStatus, _stable_content_hash
from .paths import PredictionMarketPaths, default_prediction_market_paths
from .storage import utc_isoformat


MIN_POLICY_COMPLETENESS_SCORE_FOR_FORECAST = 0.6
MIN_POLICY_COHERENCE_SCORE_FOR_FORECAST = 0.6


class ResolutionGuardReport(BaseModel):
    schema_version: str = "v1"
    market_id: str
    venue: str
    policy_id: str | None = None
    approved: bool = False
    can_forecast: bool = False
    manual_review_required: bool = True
    reasons: list[str] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)
    official_source: str | None = None
    official_source_url: str | None = None
    next_review_at: str | None = None
    status: ResolutionStatus = ResolutionStatus.unavailable
    no_trade: bool = True
    policy_completeness_score: float = 0.0
    policy_coherence_score: float = 0.0
    required_fields_count: int = 0
    present_fields_count: int = 0
    missing_fields: list[str] = Field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResolutionPolicySurface(BaseModel):
    schema_version: str = "v1"
    market_id: str
    venue: str
    policy_id: str | None = None
    policy_complete: bool = False
    policy_completeness_score: float = 0.0
    policy_coherent: bool = False
    policy_coherence_score: float = 0.0
    approved: bool = False
    can_forecast: bool = False
    no_trade: bool = True
    manual_review_required: bool = True
    status: ResolutionStatus = ResolutionStatus.unavailable
    official_source: str | None = None
    official_source_url: str | None = None
    source_url: str | None = None
    next_review_at: str | None = None
    required_fields_count: int = 0
    present_fields_count: int = 0
    missing_fields: list[str] = Field(default_factory=list)
    completeness_flags: list[str] = Field(default_factory=list)
    coherence_flags: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)
    snapshot_status: str | None = None
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "ResolutionPolicySurface":
        self.missing_fields = list(dict.fromkeys(self.missing_fields))
        self.completeness_flags = [flag for flag in dict.fromkeys(self.completeness_flags) if flag]
        self.coherence_flags = [flag for flag in dict.fromkeys(self.coherence_flags) if flag]
        self.reasons = [reason for reason in dict.fromkeys(self.reasons) if reason]
        self.ambiguity_flags = [flag for flag in dict.fromkeys(self.ambiguity_flags) if flag]
        if not self.content_hash:
            self.content_hash = _stable_content_hash(
                {
                    **self.model_dump(mode="json", exclude_none=True),
                    "content_hash": "",
                }
            )
        return self


class ResolutionPolicyCompletenessReport(BaseModel):
    schema_version: str = "v1"
    report_id: str = Field(default_factory=lambda: "respol_completeness")
    market_count: int = 0
    policy_count: int = 0
    complete_count: int = 0
    coherent_count: int = 0
    no_trade_count: int = 0
    approved_count: int = 0
    clear_count: int = 0
    ambiguous_count: int = 0
    manual_review_count: int = 0
    unavailable_count: int = 0
    complete_rate: float = 0.0
    coherent_rate: float = 0.0
    approved_rate: float = 0.0
    manual_review_rate: float = 0.0
    ambiguous_rate: float = 0.0
    unavailable_rate: float = 0.0
    mean_policy_completeness_score: float = 0.0
    mean_policy_coherence_score: float = 0.0
    surfaces: list[ResolutionPolicySurface] = Field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "ResolutionPolicyCompletenessReport":
        self.market_count = max(0, int(self.market_count))
        self.policy_count = max(0, int(self.policy_count))
        self.complete_count = max(0, int(self.complete_count))
        self.coherent_count = max(0, int(self.coherent_count))
        self.no_trade_count = max(0, int(self.no_trade_count))
        self.approved_count = max(0, int(self.approved_count))
        self.clear_count = max(0, int(self.clear_count))
        self.ambiguous_count = max(0, int(self.ambiguous_count))
        self.manual_review_count = max(0, int(self.manual_review_count))
        self.unavailable_count = max(0, int(self.unavailable_count))
        self.complete_rate = max(0.0, min(1.0, float(self.complete_rate)))
        self.coherent_rate = max(0.0, min(1.0, float(self.coherent_rate)))
        self.approved_rate = max(0.0, min(1.0, float(self.approved_rate)))
        self.manual_review_rate = max(0.0, min(1.0, float(self.manual_review_rate)))
        self.ambiguous_rate = max(0.0, min(1.0, float(self.ambiguous_rate)))
        self.unavailable_rate = max(0.0, min(1.0, float(self.unavailable_rate)))
        self.mean_policy_completeness_score = max(0.0, min(1.0, float(self.mean_policy_completeness_score)))
        self.mean_policy_coherence_score = max(0.0, min(1.0, float(self.mean_policy_coherence_score)))
        self.surfaces = sorted(
            self.surfaces,
            key=lambda item: (item.market_id, item.policy_id or "", getattr(item, "content_hash", "")),
        )
        if not self.content_hash:
            self.content_hash = _stable_content_hash(
                {
                    **self.model_dump(mode="json", exclude_none=True),
                    "report_id": "",
                    "content_hash": "",
                }
            )
        return self


def _policy_field_status(policy: ResolutionPolicy | None) -> tuple[list[str], list[str], int, int]:
    required_fields = [
        "official_source",
        "source_url",
        "resolution_rules",
        "rule_text",
        "resolution_authority",
        "source_refs",
        "cached_at",
        "last_verified_at",
    ]
    if policy is None:
        return required_fields, required_fields, len(required_fields), 0
    missing: list[str] = []
    present = 0
    for field in required_fields:
        value = getattr(policy, field, None)
        if value is None:
            missing.append(field)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(field)
            continue
        if isinstance(value, (list, tuple, set, dict)) and not value:
            missing.append(field)
            continue
        present += 1
    return required_fields, missing, len(required_fields), present


def _policy_completeness_score(policy: ResolutionPolicy | None) -> float:
    required_fields, missing_fields, total, present = _policy_field_status(policy)
    if total <= 0:
        return 0.0
    base = present / total
    if policy is None:
        return 0.0
    penalties = 0.0
    if policy.manual_review_required:
        penalties += 0.15
    if policy.status == ResolutionStatus.unavailable:
        penalties += 0.25
    if policy.ambiguity_flags:
        penalties += min(0.2, 0.05 * len(policy.ambiguity_flags))
    if not policy.official_source:
        penalties += 0.25
    return max(0.0, min(1.0, base - penalties))


def _policy_coherence_score(guard: ResolutionGuardReport, policy: ResolutionPolicy | None = None, snapshot: MarketSnapshot | None = None) -> float:
    score = 1.0
    if not guard.approved:
        score -= 0.3
    if not guard.can_forecast:
        score -= 0.2
    if guard.manual_review_required:
        score -= 0.2
    if guard.status in {ResolutionStatus.ambiguous, ResolutionStatus.unavailable}:
        score -= 0.25
    if not guard.official_source:
        score -= 0.2
    if snapshot is not None and snapshot.status not in {MarketStatus.open, MarketStatus.resolved}:
        score -= 0.1
    if policy is not None and policy.resolution_rules and not policy.rule_text:
        score -= 0.1
    return max(0.0, min(1.0, score))


def _build_policy_from_market(market: MarketDescriptor, snapshot: MarketSnapshot | None = None) -> ResolutionPolicy:
    question = (market.question or market.title or "").lower()
    ambiguity_flags: list[str] = []
    if not market.resolution_source:
        ambiguity_flags.append("missing_resolution_source")
    if any(token in question for token in ("eventually", "somehow", "somewhat", "vague", "roughly", "approximately")):
        ambiguity_flags.append("ambiguous_language")
    return ResolutionPolicy(
        market_id=market.market_id,
        venue=market.venue,
        official_source=market.resolution_source or "",
        source_url=market.source_url,
        resolution_rules=["resolution_source_present" if market.resolution_source else "missing_resolution_source"],
        ambiguity_flags=ambiguity_flags,
        manual_review_required=bool(ambiguity_flags) or not bool(market.resolution_source),
        status=ResolutionStatus.clear if not ambiguity_flags and market.resolution_source else ResolutionStatus.ambiguous if ambiguity_flags else ResolutionStatus.unavailable,
        metadata={
            "generated_by": "build_policy_from_market",
            "snapshot_status": snapshot.status.value if snapshot is not None else None,
        },
    )


class ResolutionPolicyCache:
    def __init__(self, paths: PredictionMarketPaths | None = None) -> None:
        self.paths = paths or default_prediction_market_paths()
        self.paths.ensure_layout()

    def load(self) -> dict[str, ResolutionPolicy]:
        path = self.paths.resolution_cache_path
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        return {key: ResolutionPolicy.model_validate(value) for key, value in raw.items()}

    def save(self, policies: dict[str, ResolutionPolicy]) -> Path:
        path = self.paths.resolution_cache_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: value.model_dump(mode="json") for key, value in policies.items()}
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(path)
        return path

    def get(self, market_id: str) -> ResolutionPolicy | None:
        return self.load().get(market_id)

    def set(self, policy: ResolutionPolicy) -> ResolutionPolicy:
        policies = self.load()
        policies[policy.market_id] = policy
        self.save(policies)
        return policy


class ResolutionGuard:
    def __init__(self, cache: ResolutionPolicyCache | None = None) -> None:
        self.cache = cache or ResolutionPolicyCache()

    def evaluate(
        self,
        market: MarketDescriptor,
        *,
        policy: ResolutionPolicy | None = None,
        snapshot: MarketSnapshot | None = None,
    ) -> ResolutionGuardReport:
        resolved_policy = policy or self.cache.get(market.market_id)
        required_fields: list[str] = []
        missing_fields: list[str] = []
        required_fields_count = 0
        present_fields_count = 0
        reasons: list[str] = []
        ambiguity_flags: list[str] = []
        manual_review_required = False
        approved = False
        status = ResolutionStatus.unavailable

        if resolved_policy is None:
            required_fields, missing_fields, required_fields_count, present_fields_count = _policy_field_status(None)
            reasons.append("missing_resolution_policy")
            manual_review_required = True
        else:
            required_fields, missing_fields, required_fields_count, present_fields_count = _policy_field_status(resolved_policy)
            reasons.extend(resolved_policy.resolution_rules[:3] or ["resolution_rules_loaded"])
            ambiguity_flags = list(resolved_policy.ambiguity_flags)
            manual_review_required = resolved_policy.manual_review_required
            status = resolved_policy.status
            approved = resolved_policy.status == ResolutionStatus.clear and not resolved_policy.manual_review_required
            if resolved_policy.status in {ResolutionStatus.ambiguous, ResolutionStatus.manual_review}:
                reasons.append("resolution_ambiguous")
            if not resolved_policy.official_source:
                reasons.append("missing_official_source")
                manual_review_required = True
                approved = False

        if snapshot and snapshot.status not in {MarketStatus.open, MarketStatus.resolved}:
            reasons.append(f"market_status_{snapshot.status.value}")

        if market.status in {MarketStatus.closed, MarketStatus.cancelled}:
            reasons.append(f"market_{market.status.value}")

        if ambiguity_flags:
            manual_review_required = True
            approved = False

        policy_completeness_score = _policy_completeness_score(resolved_policy)
        official_source_url = (resolved_policy.source_url if resolved_policy else None) or market.source_url
        next_review_at = utc_isoformat(resolved_policy.next_review_at if resolved_policy is not None else None)
        if resolved_policy is not None and policy_completeness_score <= MIN_POLICY_COMPLETENESS_SCORE_FOR_FORECAST:
            reasons.append("resolution_policy_incomplete")
            manual_review_required = True
            approved = False

        if manual_review_required and status == ResolutionStatus.clear:
            status = ResolutionStatus.manual_review
        if not approved and status == ResolutionStatus.unavailable and resolved_policy is not None:
            status = resolved_policy.status

        can_forecast = approved and not manual_review_required and market.status in {MarketStatus.open, MarketStatus.resolved}
        policy_coherence_score = _policy_coherence_score(
            ResolutionGuardReport(
                market_id=market.market_id,
                venue=market.venue.value,
                policy_id=resolved_policy.policy_id if resolved_policy else None,
                approved=approved,
                can_forecast=can_forecast,
                manual_review_required=manual_review_required,
                reasons=list(reasons),
                ambiguity_flags=list(ambiguity_flags),
                official_source=(resolved_policy.official_source if resolved_policy else market.resolution_source),
                official_source_url=official_source_url,
                next_review_at=next_review_at,
                status=status,
                required_fields_count=required_fields_count,
                present_fields_count=present_fields_count,
                missing_fields=list(missing_fields),
            ),
            policy=resolved_policy,
            snapshot=snapshot,
        )
        if resolved_policy is not None and policy_coherence_score <= MIN_POLICY_COHERENCE_SCORE_FOR_FORECAST:
            reasons.append("resolution_policy_incoherent")
            manual_review_required = True
            approved = False
            if status == ResolutionStatus.clear:
                status = ResolutionStatus.manual_review
            can_forecast = False

        can_forecast = approved and not manual_review_required and market.status in {MarketStatus.open, MarketStatus.resolved}
        no_trade = not can_forecast or manual_review_required or status != ResolutionStatus.clear
        summary = (
            f"status={status.value}; approved={approved}; manual_review_required={manual_review_required}; "
            f"no_trade={no_trade}; completeness={policy_completeness_score:.3f}; coherence={policy_coherence_score:.3f}"
        )

        return ResolutionGuardReport(
            market_id=market.market_id,
            venue=market.venue.value,
            policy_id=resolved_policy.policy_id if resolved_policy else None,
            approved=approved,
            can_forecast=can_forecast,
            manual_review_required=manual_review_required,
            reasons=reasons,
            ambiguity_flags=ambiguity_flags,
            official_source=(resolved_policy.official_source if resolved_policy else market.resolution_source),
            official_source_url=official_source_url,
            next_review_at=next_review_at,
            status=status,
            no_trade=no_trade,
            policy_completeness_score=policy_completeness_score,
            policy_coherence_score=policy_coherence_score,
            required_fields_count=required_fields_count,
            present_fields_count=present_fields_count,
            missing_fields=missing_fields,
            summary=summary,
            metadata={
                "source_url": official_source_url,
                "required_fields": required_fields,
                "required_fields_count": required_fields_count,
                "present_fields_count": present_fields_count,
                "missing_fields": missing_fields,
                "summary": summary,
            },
        )


AMBIGUOUS_LANGUAGE_TOKENS = (
    "eventually",
    "sometime",
    "something",
    "vague",
    "vaguely",
    "positive",
    "positively",
    "negative",
    "negatively",
    "major",
    "significant",
)


def evaluate_resolution_policy(
    market: MarketDescriptor,
    *,
    snapshot: MarketSnapshot | None = None,
) -> ResolutionGuardReport:
    policy = _build_policy_from_market(market, snapshot=snapshot)
    return ResolutionGuard(cache=None).evaluate(market, policy=policy, snapshot=snapshot)


def describe_resolution_policy_surface(
    market: MarketDescriptor,
    *,
    policy: ResolutionPolicy | None = None,
    snapshot: MarketSnapshot | None = None,
) -> ResolutionPolicySurface:
    resolved_policy = policy or _build_policy_from_market(market, snapshot=snapshot)
    guard = ResolutionGuard(cache=None).evaluate(market, policy=resolved_policy, snapshot=snapshot)
    required_fields, missing_fields, required_count, present_count = _policy_field_status(resolved_policy)
    completeness_score = _policy_completeness_score(resolved_policy)
    coherence_score = guard.policy_coherence_score or _policy_coherence_score(guard, policy=resolved_policy, snapshot=snapshot)
    official_source_url = resolved_policy.source_url or market.source_url
    next_review_at = utc_isoformat(resolved_policy.next_review_at)
    completeness_flags = [
        flag
        for flag in [
            "missing_official_source" if not resolved_policy.official_source else "",
            "missing_source_url" if not resolved_policy.source_url else "",
            "missing_resolution_rules" if not resolved_policy.resolution_rules else "",
            "missing_rule_text" if not resolved_policy.rule_text else "",
            "missing_resolution_authority" if not resolved_policy.resolution_authority else "",
            "missing_source_refs" if not resolved_policy.source_refs else "",
            "missing_cached_at" if not resolved_policy.cached_at else "",
            "missing_last_verified_at" if not resolved_policy.last_verified_at else "",
            "policy_completeness_below_forecast_threshold" if completeness_score <= MIN_POLICY_COMPLETENESS_SCORE_FOR_FORECAST else "",
        ]
        if flag
    ]
    summary = (
        f"status={guard.status.value}; approved={guard.approved}; manual_review_required={guard.manual_review_required}; "
        f"no_trade={guard.no_trade}; completeness={completeness_score:.3f}; coherence={coherence_score:.3f}"
    )
    return ResolutionPolicySurface(
        market_id=market.market_id,
        venue=market.venue.value,
        policy_id=resolved_policy.policy_id if resolved_policy else None,
        policy_complete=not missing_fields and guard.status == ResolutionStatus.clear and guard.approved and not guard.manual_review_required,
        policy_completeness_score=completeness_score,
        policy_coherent=guard.approved and guard.can_forecast and not guard.manual_review_required and guard.status == ResolutionStatus.clear,
        policy_coherence_score=coherence_score,
        approved=guard.approved,
        can_forecast=guard.can_forecast,
        no_trade=guard.no_trade,
        manual_review_required=guard.manual_review_required,
        status=guard.status,
        official_source=guard.official_source,
        official_source_url=official_source_url,
        source_url=resolved_policy.source_url,
        next_review_at=next_review_at,
        required_fields_count=required_count,
        present_fields_count=present_count,
        missing_fields=missing_fields,
        completeness_flags=completeness_flags,
        coherence_flags=list(guard.ambiguity_flags)
        + (["manual_review_required"] if guard.manual_review_required else [])
        + (["not_clear"] if guard.status != ResolutionStatus.clear else [])
        + (["no_trade"] if guard.no_trade else [])
        + (["policy_coherence_below_forecast_threshold"] if coherence_score <= MIN_POLICY_COHERENCE_SCORE_FOR_FORECAST else []),
        reasons=list(guard.reasons),
        ambiguity_flags=list(guard.ambiguity_flags),
        snapshot_status=snapshot.status.value if snapshot is not None else None,
        summary=summary,
        metadata={
            "market_status": market.status.value,
            "snapshot_status": snapshot.status.value if snapshot is not None else None,
            "policy_status": resolved_policy.status.value,
            "policy_complete": not missing_fields,
            "official_source_url": official_source_url,
            "next_review_at": next_review_at,
            "summary": summary,
        },
    )


def build_resolution_policy_completeness_report(
    markets: list[MarketDescriptor],
    *,
    policies: dict[str, ResolutionPolicy] | None = None,
    snapshots: dict[str, MarketSnapshot] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ResolutionPolicyCompletenessReport:
    policy_map = dict(policies or {})
    snapshot_map = dict(snapshots or {})
    surfaces: list[ResolutionPolicySurface] = []
    for market in markets:
        surface = describe_resolution_policy_surface(
            market,
            policy=policy_map.get(market.market_id),
            snapshot=snapshot_map.get(market.market_id),
        )
        surfaces.append(surface)
    total = len(surfaces)
    if total == 0:
        return ResolutionPolicyCompletenessReport(metadata=dict(metadata or {}))._normalize()
    policy_count = sum(1 for surface in surfaces if surface.policy_id is not None)
    complete_count = sum(1 for surface in surfaces if surface.policy_complete)
    coherent_count = sum(1 for surface in surfaces if surface.policy_coherent)
    no_trade_count = sum(1 for surface in surfaces if surface.no_trade)
    approved_count = sum(1 for surface in surfaces if surface.approved)
    clear_count = sum(1 for surface in surfaces if surface.status == ResolutionStatus.clear)
    ambiguous_count = sum(1 for surface in surfaces if surface.status == ResolutionStatus.ambiguous)
    manual_review_count = sum(1 for surface in surfaces if surface.status == ResolutionStatus.manual_review)
    unavailable_count = sum(1 for surface in surfaces if surface.status == ResolutionStatus.unavailable)
    summary = (
        f"{complete_count}/{total} complete; {coherent_count}/{total} coherent; "
        f"{manual_review_count}/{total} manual_review; {no_trade_count}/{total} no_trade"
    )
    return ResolutionPolicyCompletenessReport(
        market_count=total,
        policy_count=policy_count,
        complete_count=complete_count,
        coherent_count=coherent_count,
        no_trade_count=no_trade_count,
        approved_count=approved_count,
        clear_count=clear_count,
        ambiguous_count=ambiguous_count,
        manual_review_count=manual_review_count,
        unavailable_count=unavailable_count,
        complete_rate=complete_count / total,
        coherent_rate=coherent_count / total,
        approved_rate=approved_count / total,
        manual_review_rate=manual_review_count / total,
        ambiguous_rate=ambiguous_count / total,
        unavailable_rate=unavailable_count / total,
        mean_policy_completeness_score=sum(surface.policy_completeness_score for surface in surfaces) / total,
        mean_policy_coherence_score=sum(surface.policy_coherence_score for surface in surfaces) / total,
        surfaces=surfaces,
        summary=summary,
        metadata=dict(metadata or {}),
    )._normalize()
