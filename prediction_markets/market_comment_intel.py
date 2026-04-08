from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .models import SourceKind, VenueName


POSITIVE_WORDS = {
    "bull",
    "bullish",
    "buy",
    "green",
    "gain",
    "good",
    "great",
    "higher",
    "improve",
    "long",
    "moon",
    "positive",
    "pump",
    "win",
    "yes",
    "support",
    "strong",
}

NEGATIVE_WORDS = {
    "bear",
    "bearish",
    "bad",
    "down",
    "drop",
    "fear",
    "lower",
    "negative",
    "no",
    "risk",
    "sell",
    "short",
    "weak",
    "worry",
    "concern",
    "crash",
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "for",
    "from",
    "i",
    "if",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "will",
    "with",
    "you",
}

TOKEN_RE = re.compile(r"[a-z0-9']+")


class CommentSentimentLabel(str, Enum):
    bullish = "bullish"
    bearish = "bearish"
    mixed = "mixed"
    neutral = "neutral"


class CommentRecord(BaseModel):
    schema_version: str = "v1"
    comment_id: str = Field(default_factory=lambda: f"comment_{uuid4().hex[:12]}")
    author: str | None = None
    text: str
    source_kind: SourceKind = SourceKind.social
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    replies: int = 0
    engagement_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def _normalize_text(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("comment text cannot be empty")
        return text

    @field_validator("replies")
    @classmethod
    def _normalize_replies(cls, value: int) -> int:
        return max(0, int(value or 0))


class CommentSentimentSummary(BaseModel):
    schema_version: str = "v1"
    score: float = 0.0
    label: CommentSentimentLabel = CommentSentimentLabel.neutral
    confidence: float = 0.0
    bullish_comment_share: float = 0.0
    bearish_comment_share: float = 0.0
    neutral_comment_share: float = 0.0
    positive_term_hits: int = 0
    negative_term_hits: int = 0
    representative_terms: list[str] = Field(default_factory=list)
    signal_notes: list[str] = Field(default_factory=list)

    @field_validator("score", "confidence", "bullish_comment_share", "bearish_comment_share", "neutral_comment_share")
    @classmethod
    def _clamp_probability(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value))) if value >= 0 else max(-1.0, min(1.0, float(value)))


class NarrativeSignal(BaseModel):
    schema_version: str = "v1"
    narrative_id: str = Field(default_factory=lambda: f"nar_{uuid4().hex[:12]}")
    direction: CommentSentimentLabel = CommentSentimentLabel.neutral
    title: str
    summary: str
    strength: float = 0.0
    keywords: list[str] = Field(default_factory=list)
    comment_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("strength")
    @classmethod
    def _clamp_strength(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))


class MarketCommentIntelReport(BaseModel):
    schema_version: str = "v1"
    report_id: str = Field(default_factory=lambda: f"mci_{uuid4().hex[:12]}")
    market_id: str
    venue: VenueName = VenueName.custom
    market_title: str = ""
    market_question: str = ""
    comment_count: int = 0
    author_count: int = 0
    source_kind_counts: dict[str, int] = Field(default_factory=dict)
    sentiment: CommentSentimentSummary = Field(default_factory=CommentSentimentSummary)
    dominant_narrative: NarrativeSignal | None = None
    counter_narratives: list[NarrativeSignal] = Field(default_factory=list)
    top_terms: list[str] = Field(default_factory=list)
    narrative_summary: str = ""
    comment_ids: list[str] = Field(default_factory=list)
    sample_comments: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MarketCommentIntel:
    def analyze(
        self,
        comments: Iterable[str | dict[str, Any] | CommentRecord],
        *,
        market_id: str,
        venue: VenueName = VenueName.custom,
        market_title: str = "",
        market_question: str = "",
        max_samples: int = 3,
    ) -> MarketCommentIntelReport:
        records = [self._normalize_comment(comment) for comment in comments]
        if not records:
            return MarketCommentIntelReport(
                market_id=market_id,
                venue=venue,
                market_title=market_title,
                market_question=market_question,
                narrative_summary="No comments available.",
            )

        scored = [self._score_comment(record) for record in records]
        weighted_score = self._weighted_sentiment(scored)
        label = self._label_for_score(weighted_score)
        positive_share, negative_share, neutral_share = self._share_counts(scored)
        sentiment = CommentSentimentSummary(
            score=weighted_score,
            label=label,
            confidence=self._confidence(scored, positive_share, negative_share),
            bullish_comment_share=positive_share,
            bearish_comment_share=negative_share,
            neutral_comment_share=neutral_share,
            positive_term_hits=sum(item["positive_hits"] for item in scored),
            negative_term_hits=sum(item["negative_hits"] for item in scored),
            representative_terms=self._top_terms(scored),
            signal_notes=self._signal_notes(scored, label),
        )
        dominant_narrative = self._dominant_narrative(records, scored, label, market_title, market_question)
        counter_narratives = self._counter_narratives(records, scored, label, market_title, market_question)
        source_kind_counts = Counter(record.source_kind.value for record in records)
        top_terms = self._top_terms(scored, limit=8)
        sample_comments = [record.text for record in records[: max(1, min(max_samples, len(records)))]]
        narrative_summary = self._build_summary_text(
            market_title=market_title or market_id,
            comment_count=len(records),
            author_count=len({record.author for record in records if record.author}),
            sentiment=sentiment,
            dominant_narrative=dominant_narrative,
        )
        return MarketCommentIntelReport(
            market_id=market_id,
            venue=venue,
            market_title=market_title,
            market_question=market_question,
            comment_count=len(records),
            author_count=len({record.author for record in records if record.author}),
            source_kind_counts=dict(sorted(source_kind_counts.items())),
            sentiment=sentiment,
            dominant_narrative=dominant_narrative,
            counter_narratives=counter_narratives,
            top_terms=top_terms,
            narrative_summary=narrative_summary,
            comment_ids=[record.comment_id for record in records],
            sample_comments=sample_comments,
            metadata={
                "market_terms": self._market_terms(market_title, market_question),
                "unique_authors": len({record.author for record in records if record.author}),
            },
        )

    def summarize_comments(self, comments: Iterable[str | dict[str, Any] | CommentRecord], *, market_id: str) -> MarketCommentIntelReport:
        return self.analyze(comments, market_id=market_id)

    @staticmethod
    def _normalize_comment(comment: str | dict[str, Any] | CommentRecord) -> CommentRecord:
        if isinstance(comment, CommentRecord):
            return comment
        if isinstance(comment, str):
            return CommentRecord(text=comment)
        payload = dict(comment)
        text = str(payload.get("text") or payload.get("body") or payload.get("content") or payload.get("message") or "").strip()
        if not text:
            raise ValueError("comment text cannot be empty")
        created_at = payload.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at_value = datetime.fromisoformat(created_at)
            except ValueError:
                created_at_value = datetime.now(timezone.utc)
        elif isinstance(created_at, datetime):
            created_at_value = created_at
        else:
            created_at_value = datetime.now(timezone.utc)
        source_kind = payload.get("source_kind") or payload.get("source") or SourceKind.social
        if isinstance(source_kind, str):
            try:
                source_kind = SourceKind(source_kind)
            except ValueError:
                source_kind = SourceKind.other
        return CommentRecord(
            comment_id=str(payload.get("comment_id") or payload.get("id") or f"comment_{uuid4().hex[:12]}"),
            author=payload.get("author") or payload.get("user") or payload.get("username"),
            text=text,
            source_kind=source_kind,
            created_at=created_at_value,
            replies=int(payload.get("replies") or payload.get("reply_count") or 0),
            engagement_score=payload.get("score") if isinstance(payload.get("score"), (int, float)) else payload.get("engagement_score"),
            metadata={key: value for key, value in payload.items() if key not in {"comment_id", "id", "author", "user", "username", "text", "body", "content", "message", "source_kind", "source", "created_at", "replies", "reply_count", "score", "engagement_score"}},
        )

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [token for token in TOKEN_RE.findall(text.lower()) if token not in STOPWORDS]

    def _score_comment(self, record: CommentRecord) -> dict[str, Any]:
        tokens = self._tokenize(record.text)
        positive_hits = sum(1 for token in tokens if token in POSITIVE_WORDS)
        negative_hits = sum(1 for token in tokens if token in NEGATIVE_WORDS)
        raw_score = 0.0
        if positive_hits or negative_hits:
            raw_score = (positive_hits - negative_hits) / max(1, positive_hits + negative_hits)
        return {
            "record": record,
            "tokens": tokens,
            "positive_hits": positive_hits,
            "negative_hits": negative_hits,
            "raw_score": raw_score,
            "weight": self._comment_weight(record),
        }

    @staticmethod
    def _comment_weight(record: CommentRecord) -> float:
        weight = 1.0
        if record.engagement_score is not None:
            weight += min(1.0, max(0.0, float(record.engagement_score)) / 100.0)
        weight += min(0.5, record.replies / 10.0)
        return round(weight, 3)

    @staticmethod
    def _weighted_sentiment(scored: list[dict[str, Any]]) -> float:
        if not scored:
            return 0.0
        numerator = sum(item["raw_score"] * item["weight"] for item in scored)
        denominator = sum(item["weight"] for item in scored) or 1.0
        return round(max(-1.0, min(1.0, numerator / denominator)), 3)

    @staticmethod
    def _label_for_score(score: float) -> CommentSentimentLabel:
        if score >= 0.2:
            return CommentSentimentLabel.bullish
        if score <= -0.2:
            return CommentSentimentLabel.bearish
        if abs(score) < 0.08:
            return CommentSentimentLabel.neutral
        return CommentSentimentLabel.mixed

    @staticmethod
    def _share_counts(scored: list[dict[str, Any]]) -> tuple[float, float, float]:
        if not scored:
            return 0.0, 0.0, 0.0
        bullish = 0
        bearish = 0
        neutral = 0
        for item in scored:
            if item["raw_score"] >= 0.2:
                bullish += 1
            elif item["raw_score"] <= -0.2:
                bearish += 1
            else:
                neutral += 1
        total = float(len(scored))
        return round(bullish / total, 3), round(bearish / total, 3), round(neutral / total, 3)

    def _confidence(self, scored: list[dict[str, Any]], bullish_share: float, bearish_share: float) -> float:
        volume = len(scored)
        dominant_share = max(bullish_share, bearish_share)
        if volume == 0:
            return 0.0
        confidence = 0.28 + min(0.35, 0.08 * volume) + min(0.18, dominant_share * 0.3)
        return round(max(0.0, min(1.0, confidence)), 3)

    def _top_terms(self, scored: list[dict[str, Any]], *, limit: int = 5) -> list[str]:
        tokens = Counter(token for item in scored for token in item["tokens"] if len(token) > 2)
        return [term for term, _ in tokens.most_common(limit)]

    def _signal_notes(self, scored: list[dict[str, Any]], label: CommentSentimentLabel) -> list[str]:
        notes = [f"dominant_label={label.value}", f"comment_count={len(scored)}"]
        if any(item["positive_hits"] and item["negative_hits"] for item in scored):
            notes.append("mixed_polarity_present")
        if len(scored) >= 5:
            notes.append("sufficient_sample_size")
        return notes

    def _dominant_narrative(
        self,
        records: list[CommentRecord],
        scored: list[dict[str, Any]],
        label: CommentSentimentLabel,
        market_title: str,
        market_question: str,
    ) -> NarrativeSignal | None:
        if not scored:
            return None
        keywords = self._top_terms(scored, limit=4)
        if not keywords:
            keywords = self._market_terms(market_title, market_question)[:4] or ["thread"]
        strength = self._weighted_sentiment(scored)
        title = self._build_narrative_title(label, keywords)
        summary = self._build_narrative_summary(label, keywords, len(records))
        return NarrativeSignal(
            direction=label,
            title=title,
            summary=summary,
            strength=abs(strength),
            keywords=keywords,
            comment_ids=[record.comment_id for record in records[: max(1, min(6, len(records))) ]],
            metadata={"source": "dominant"},
        )

    def _counter_narratives(
        self,
        records: list[CommentRecord],
        scored: list[dict[str, Any]],
        label: CommentSentimentLabel,
        market_title: str,
        market_question: str,
    ) -> list[NarrativeSignal]:
        opposites = {
            CommentSentimentLabel.bullish: CommentSentimentLabel.bearish,
            CommentSentimentLabel.bearish: CommentSentimentLabel.bullish,
            CommentSentimentLabel.mixed: CommentSentimentLabel.neutral,
            CommentSentimentLabel.neutral: CommentSentimentLabel.mixed,
        }
        target_label = opposites[label]
        counter_records = [
            item["record"]
            for item in scored
            if self._label_for_score(item["raw_score"]) == target_label
        ]
        if not counter_records:
            return []
        keywords = self._top_terms([item for item in scored if item["record"] in counter_records], limit=4)
        if not keywords:
            keywords = self._market_terms(market_title, market_question)[:4] or ["counterpoint"]
        return [
            NarrativeSignal(
                direction=target_label,
                title=self._build_narrative_title(target_label, keywords),
                summary=self._build_narrative_summary(target_label, keywords, len(counter_records)),
                strength=min(1.0, 0.35 + 0.1 * len(counter_records)),
                keywords=keywords,
                comment_ids=[record.comment_id for record in counter_records[: max(1, min(4, len(counter_records))) ]],
                metadata={"source": "counter"},
            )
        ]

    @staticmethod
    def _build_narrative_title(label: CommentSentimentLabel, keywords: list[str]) -> str:
        prefix = {
            CommentSentimentLabel.bullish: "Bullish",
            CommentSentimentLabel.bearish: "Bearish",
            CommentSentimentLabel.mixed: "Mixed",
            CommentSentimentLabel.neutral: "Neutral",
        }[label]
        if keywords:
            return f"{prefix} narrative around {', '.join(keywords[:2])}"
        return f"{prefix} narrative"

    @staticmethod
    def _build_narrative_summary(label: CommentSentimentLabel, keywords: list[str], count: int) -> str:
        keyword_bits = ", ".join(keywords[:4]) if keywords else "general commentary"
        return f"{count} comments lean {label.value}, centered on {keyword_bits}."

    @staticmethod
    def _market_terms(market_title: str, market_question: str) -> list[str]:
        tokens = TOKEN_RE.findall(f"{market_title} {market_question}".lower())
        return [token for token in tokens if token not in STOPWORDS]

    @staticmethod
    def _build_summary_text(
        *,
        market_title: str,
        comment_count: int,
        author_count: int,
        sentiment: CommentSentimentSummary,
        dominant_narrative: NarrativeSignal | None,
    ) -> str:
        narrative_bits = dominant_narrative.title if dominant_narrative else "no dominant narrative"
        return (
            f"{market_title}: {comment_count} comments from {author_count} authors "
            f"lean {sentiment.label.value} (score={sentiment.score:+.3f}); {narrative_bits}."
        )
