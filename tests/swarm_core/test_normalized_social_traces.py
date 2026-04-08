from __future__ import annotations

from pathlib import Path

from swarm_core.normalized_social_traces import (
    NormalizedSocialTraceStore,
    SocialTraceKind,
    infer_trace_kind,
    infer_trace_tags,
    normalize_social_trace,
    score_social_sentiment,
)


def test_normalized_social_trace_infers_kind_sentiment_and_tags() -> None:
    trace = normalize_social_trace(
        {
            "content": "We should support the rollout and avoid a delay.",
            "actor_id": "agent_1",
            "tags": ["news"],
        },
        platform="twitter",
        round_index=1,
    )

    assert trace.kind in {SocialTraceKind.post, SocialTraceKind.signal}
    assert trace.sentiment != 0.0
    assert "twitter" in trace.tags
    assert "news" in trace.tags


def test_social_trace_store_persists_and_aggregates(tmp_path: Path) -> None:
    store = NormalizedSocialTraceStore(tmp_path / "social_traces.json")
    store.append(
        normalize_social_trace("A positive update", platform="reddit", actor_id="agent_1", kind=SocialTraceKind.comment)
    )
    store.append(
        normalize_social_trace("A risky delay", platform="twitter", actor_id="agent_2", kind=SocialTraceKind.reply)
    )

    loaded = NormalizedSocialTraceStore(tmp_path / "social_traces.json")
    aggregate = loaded.aggregate()

    assert aggregate.trace_count == 2
    assert aggregate.platform_counts["reddit"] == 1
    assert aggregate.platform_counts["twitter"] == 1
    assert aggregate.top_tags
    assert aggregate.average_score > 0.0


def test_social_trace_search_returns_relevant_matches(tmp_path: Path) -> None:
    store = NormalizedSocialTraceStore(tmp_path / "social_traces.json")
    store.extend(
        [
            normalize_social_trace("launch looks stable", platform="forum", actor_id="a"),
            normalize_social_trace("delay risk is high", platform="forum", actor_id="b"),
        ]
    )

    matches = store.search("delay risk", limit=1)
    assert len(matches) == 1
    assert matches[0].content == "delay risk is high"


def test_social_trace_helpers_are_deterministic() -> None:
    assert infer_trace_kind("This is a summary report") in {SocialTraceKind.summary, SocialTraceKind.report}
    assert score_social_sentiment("support and stable") > 0
    assert "twitter" in infer_trace_tags("support and stable", platform="twitter", kind=SocialTraceKind.post)
