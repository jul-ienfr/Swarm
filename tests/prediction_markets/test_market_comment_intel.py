from __future__ import annotations

from prediction_markets.market_comment_intel import (
    CommentSentimentLabel,
    MarketCommentIntel,
)
from prediction_markets.models import VenueName


def test_market_comment_intel_extracts_sentiment_and_narratives() -> None:
    comments = [
        "Bullish breakout, yes win and strong support.",
        {"text": "I worry about risk and a weak response.", "author": "bob", "replies": 2, "score": 7},
        "Bullish support keeps improving and higher.",
    ]

    report = MarketCommentIntel().analyze(
        comments,
        market_id="market_1",
        venue=VenueName.polymarket,
        market_title="Fed cuts market",
        market_question="Will the Fed cut rates?",
    )

    assert report.comment_count == 3
    assert report.author_count == 1
    assert report.sentiment.label in {CommentSentimentLabel.bullish, CommentSentimentLabel.mixed}
    assert report.sentiment.positive_term_hits > report.sentiment.negative_term_hits
    assert report.dominant_narrative is not None
    assert report.dominant_narrative.keywords
    assert report.narrative_summary
    assert report.sample_comments
    assert report.dominant_narrative.title
    if report.sentiment.label == CommentSentimentLabel.bullish:
        assert "bullish" in report.dominant_narrative.title.lower()


def test_market_comment_intel_normalizes_dict_inputs_and_counter_narratives() -> None:
    comments = [
        {
            "body": "No, this looks weak and bearish.",
            "user": "alice",
            "source_kind": "social",
            "created_at": "2026-04-08T00:00:00+00:00",
        },
        {
            "content": "The upside is great and support is strong.",
            "username": "carol",
            "source": "news",
        },
    ]

    report = MarketCommentIntel().analyze(
        comments,
        market_id="market_2",
        venue=VenueName.custom,
        market_title="Synthetic market",
        market_question="What happens next?",
    )

    assert report.comment_count == 2
    assert report.source_kind_counts["social"] == 1
    assert report.source_kind_counts["news"] == 1
    assert report.sentiment.label in {
        CommentSentimentLabel.bullish,
        CommentSentimentLabel.mixed,
        CommentSentimentLabel.neutral,
        CommentSentimentLabel.bearish,
    }
    assert report.comment_ids
    assert report.top_terms
    assert report.metadata["unique_authors"] == 2
