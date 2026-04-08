from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import mean
from typing import Any, Iterable
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .market_comment_intel import CommentRecord, CommentSentimentLabel, MarketCommentIntel, MarketCommentIntelReport
from .models import EvidencePacket, MarketDescriptor, MarketSnapshot, MarketStatus, ResolutionPolicy, ResolutionStatus, VenueName
from .streaming import MarketStreamHealth, MarketStreamSummary


class ManipulationGuardSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ManipulationGuardConstraints(BaseModel):
    schema_version: str = "v1"
    max_snapshot_staleness_ms: int = 120_000
    max_stream_staleness_seconds: float = 1_800.0
    max_spread_bps: float = 500.0
    min_liquidity: float = 1_000.0
    min_comment_count_for_structure: int = 3
    min_comment_count_for_burst: int = 5
    min_author_count: int = 3
    max_comments_per_author: float = 3.0
    max_dominant_share: float = 0.75
    min_signal_confidence: float = 0.55
    max_allowable_market_clarity_penalty: float = 0.55
    low_evidence_weight_threshold: float = 0.2
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("max_snapshot_staleness_ms", "min_comment_count_for_structure", "min_comment_count_for_burst", "min_author_count")
    @classmethod
    def _non_negative_int(cls, value: int) -> int:
        return max(0, int(value))

    @field_validator(
        "max_stream_staleness_seconds",
        "max_spread_bps",
        "min_liquidity",
        "max_comments_per_author",
        "max_dominant_share",
        "min_signal_confidence",
        "max_allowable_market_clarity_penalty",
        "low_evidence_weight_threshold",
    )
    @classmethod
    def _non_negative_float(cls, value: float) -> float:
        return max(0.0, float(value))


class ManipulationGuardReport(BaseModel):
    schema_version: str = "v1"
    guard_id: str = Field(default_factory=lambda: f"mguard_{uuid4().hex[:12]}")
    market_id: str
    venue: VenueName
    snapshot_id: str | None = None
    severity: ManipulationGuardSeverity = ManipulationGuardSeverity.low
    risk_score: float = 0.0
    risk_flags: list[str] = Field(default_factory=list)
    can_trade: bool = True
    signal_only: bool = False
    reasons: list[str] = Field(default_factory=list)
    comment_count: int = 0
    author_count: int = 0
    evidence_count: int = 0
    stream_event_count: int = 0
    stream_health_status: str = "unknown"
    snapshot_staleness_ms: int | None = None
    market_clarity_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("risk_score")
    @classmethod
    def _clamp_score(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))


FLAG_WEIGHTS: dict[str, float] = {
    "market_not_tradable": 0.45,
    "snapshot_not_tradable": 0.4,
    "missing_resolution_source": 0.45,
    "stale_snapshot": 0.4,
    "stream_unhealthy": 0.3,
    "stream_stale": 0.25,
    "stream_inconsistent": 0.35,
    "illiquid_market": 0.18,
    "wide_spread": 0.15,
    "thin_comment_sample": 0.12,
    "low_author_diversity": 0.2,
    "comment_burst": 0.18,
    "one_sided_comments": 0.2,
    "narrative_mismatch": 0.25,
    "narrative_only": 0.3,
    "weak_evidence": 0.18,
    "market_clarity_low": 0.12,
    "resolution_policy_unclear": 0.3,
}


def _dedupe(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _severity_from_score(score: float) -> ManipulationGuardSeverity:
    if score >= 0.8:
        return ManipulationGuardSeverity.critical
    if score >= 0.55:
        return ManipulationGuardSeverity.high
    if score >= 0.25:
        return ManipulationGuardSeverity.medium
    return ManipulationGuardSeverity.low


@dataclass
class ManipulationGuard:
    constraints: ManipulationGuardConstraints | None = None
    comment_intel: MarketCommentIntel | None = None

    def __post_init__(self) -> None:
        self.constraints = self.constraints or ManipulationGuardConstraints()
        self.comment_intel = self.comment_intel or MarketCommentIntel()

    def evaluate(
        self,
        market: MarketDescriptor,
        snapshot: MarketSnapshot,
        *,
        comments: Iterable[str | dict[str, Any] | CommentRecord] | None = None,
        comment_report: MarketCommentIntelReport | None = None,
        stream_summary: MarketStreamSummary | None = None,
        stream_health: MarketStreamHealth | None = None,
        evidence: Iterable[EvidencePacket] | None = None,
        resolution_policy: ResolutionPolicy | None = None,
    ) -> ManipulationGuardReport:
        constraints = self.constraints or ManipulationGuardConstraints()
        evidence_list = list(evidence or [])

        if comment_report is None and comments is not None:
            comment_report = self.comment_intel.analyze(
                comments,
                market_id=market.market_id,
                venue=market.venue,
                market_title=market.title,
                market_question=market.question,
            )

        risk_flags: list[str] = []
        reasons: list[str] = []
        risk_score = 0.0

        def add_flag(flag: str, reason: str | None = None) -> None:
            nonlocal risk_score
            if flag not in risk_flags:
                risk_flags.append(flag)
                risk_score += FLAG_WEIGHTS.get(flag, 0.1)
                reasons.append(reason or flag)

        if market.status not in {MarketStatus.open, MarketStatus.resolved}:
            add_flag("market_not_tradable", f"market_status={market.status.value}")
        if snapshot.status not in {MarketStatus.open, MarketStatus.resolved}:
            add_flag("snapshot_not_tradable", f"snapshot_status={snapshot.status.value}")

        if not market.resolution_source:
            add_flag("missing_resolution_source", "missing_resolution_source")
        elif resolution_policy is not None and (
            resolution_policy.status != ResolutionStatus.clear or resolution_policy.manual_review_required
        ):
            add_flag("resolution_policy_unclear", f"resolution_status={resolution_policy.status.value}")

        if snapshot.staleness_ms is not None and snapshot.staleness_ms > constraints.max_snapshot_staleness_ms:
            add_flag("stale_snapshot", f"snapshot_staleness_ms={snapshot.staleness_ms}")
        if snapshot.liquidity is not None and snapshot.liquidity < constraints.min_liquidity:
            add_flag("illiquid_market", f"liquidity={snapshot.liquidity:.2f}")
        if snapshot.spread_bps is not None and snapshot.spread_bps > constraints.max_spread_bps:
            add_flag("wide_spread", f"spread_bps={snapshot.spread_bps:.2f}")

        if stream_health is not None:
            if not stream_health.healthy:
                add_flag("stream_unhealthy", stream_health.message)
            if stream_health.freshness_status in {"stale", "empty"}:
                add_flag("stream_stale", f"freshness_status={stream_health.freshness_status}")
            if any(issue in {"manifest_event_mismatch", "sequence_mismatch", "snapshot_market_mismatch"} for issue in stream_health.issues):
                add_flag("stream_inconsistent", ",".join(stream_health.issues))
        elif stream_summary is not None and stream_summary.event_count <= 0:
            add_flag("stream_stale", "stream_has_no_events")

        if comment_report is not None:
            if comment_report.comment_count > 0 and comment_report.comment_count < constraints.min_comment_count_for_structure:
                add_flag("thin_comment_sample", f"comment_count={comment_report.comment_count}")
            if comment_report.comment_count >= constraints.min_comment_count_for_burst and comment_report.author_count <= constraints.min_author_count:
                add_flag("low_author_diversity", f"author_count={comment_report.author_count}")

            if (
                comment_report.comment_count >= constraints.min_comment_count_for_burst
                and comment_report.author_count > 0
                and comment_report.comment_count / comment_report.author_count >= constraints.max_comments_per_author
            ):
                add_flag("comment_burst", f"comment_to_author_ratio={comment_report.comment_count / comment_report.author_count:.2f}")

            sentiment = comment_report.sentiment
            if sentiment.confidence >= constraints.min_signal_confidence:
                dominant_share = max(
                    sentiment.bullish_comment_share,
                    sentiment.bearish_comment_share,
                    sentiment.neutral_comment_share,
                )
                if dominant_share >= constraints.max_dominant_share:
                    add_flag("one_sided_comments", f"dominant_share={dominant_share:.2f}")

            if comment_report.dominant_narrative is not None:
                dominant = comment_report.dominant_narrative
                if dominant.strength >= constraints.min_signal_confidence and not comment_report.counter_narratives:
                    add_flag("narrative_only", "single_narrative_without_counterbalance")
                    add_flag("weak_evidence", "single_narrative_without_counterbalance")

                if stream_summary is not None:
                    if (
                        dominant.direction == CommentSentimentLabel.bullish
                        and stream_summary.trend == "bearish"
                    ) or (
                        dominant.direction == CommentSentimentLabel.bearish
                        and stream_summary.trend == "bullish"
                    ):
                        add_flag("narrative_mismatch", f"comment_trend={dominant.direction.value},stream_trend={stream_summary.trend}")

                if snapshot.market_implied_probability is not None:
                    if dominant.direction == CommentSentimentLabel.bullish and snapshot.market_implied_probability < 0.45:
                        add_flag("narrative_mismatch", f"comment_bullish_vs_snapshot_prob={snapshot.market_implied_probability:.3f}")
                    if dominant.direction == CommentSentimentLabel.bearish and snapshot.market_implied_probability > 0.55:
                        add_flag("narrative_mismatch", f"comment_bearish_vs_snapshot_prob={snapshot.market_implied_probability:.3f}")

            if sentiment.confidence < 0.25 and comment_report.comment_count >= constraints.min_comment_count_for_structure:
                add_flag("weak_evidence", f"sentiment_confidence={sentiment.confidence:.2f}")

        if evidence_list:
            average_weight = mean(packet.evidence_weight for packet in evidence_list)
            if average_weight < constraints.low_evidence_weight_threshold:
                add_flag("weak_evidence", f"evidence_weight={average_weight:.3f}")

        market_clarity = market.clarity_score
        if market_clarity < constraints.max_allowable_market_clarity_penalty:
            add_flag("market_clarity_low", f"clarity_score={market_clarity:.3f}")

        risk_score = min(1.0, risk_score)
        if not risk_flags:
            reasons.append("context_balanced")

        severity = _severity_from_score(risk_score)
        hard_blocks = {
            "market_not_tradable",
            "snapshot_not_tradable",
            "missing_resolution_source",
            "stale_snapshot",
            "stream_inconsistent",
            "stream_unhealthy",
            "resolution_policy_unclear",
        }
        can_trade = severity == ManipulationGuardSeverity.low and not any(flag in hard_blocks for flag in risk_flags)
        signal_only = not can_trade

        return ManipulationGuardReport(
            market_id=market.market_id,
            venue=market.venue,
            snapshot_id=snapshot.snapshot_id,
            severity=severity,
            risk_score=risk_score,
            risk_flags=_dedupe(risk_flags),
            can_trade=can_trade,
            signal_only=signal_only,
            reasons=_dedupe(reasons),
            comment_count=comment_report.comment_count if comment_report is not None else 0,
            author_count=comment_report.author_count if comment_report is not None else 0,
            evidence_count=len(evidence_list),
            stream_event_count=stream_summary.event_count if stream_summary is not None else 0,
            stream_health_status=stream_health.freshness_status if stream_health is not None else ("present" if stream_summary is not None else "unknown"),
            snapshot_staleness_ms=snapshot.staleness_ms,
            market_clarity_score=market_clarity,
            metadata={
                "market_status": market.status.value,
                "snapshot_status": snapshot.status.value,
                "market_title": market.title,
                "comment_report_id": comment_report.report_id if comment_report is not None else None,
                "stream_id": stream_summary.stream_id if stream_summary is not None else None,
                "stream_health_issues": list(stream_health.issues) if stream_health is not None else [],
                "constraints": constraints.model_dump(mode="json"),
            },
        )


def evaluate_manipulation_guard(
    market: MarketDescriptor,
    snapshot: MarketSnapshot,
    *,
    comments: Iterable[str | dict[str, Any] | CommentRecord] | None = None,
    comment_report: MarketCommentIntelReport | None = None,
    stream_summary: MarketStreamSummary | None = None,
    stream_health: MarketStreamHealth | None = None,
    evidence: Iterable[EvidencePacket] | None = None,
    resolution_policy: ResolutionPolicy | None = None,
    constraints: ManipulationGuardConstraints | None = None,
) -> ManipulationGuardReport:
    return ManipulationGuard(constraints=constraints).evaluate(
        market,
        snapshot,
        comments=comments,
        comment_report=comment_report,
        stream_summary=stream_summary,
        stream_health=stream_health,
        evidence=evidence,
        resolution_policy=resolution_policy,
    )
