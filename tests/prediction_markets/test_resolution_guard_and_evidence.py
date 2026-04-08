from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from prediction_markets import (
    EvidenceRegistry,
    PolymarketAdapter,
    PredictionMarketPaths,
    ResearchCollector,
    ResolutionGuard,
    ResolutionPolicyCache,
    ResolutionStatus,
)
from prediction_markets.resolution_guard import (
    ResolutionPolicyCompletenessReport,
    describe_resolution_policy_surface,
    build_resolution_policy_completeness_report,
)


def test_resolution_guard_approves_clear_markets() -> None:
    adapter = PolymarketAdapter(backend_mode="surrogate")
    market = adapter.get_market("polymarket-fed-cut-q3-2026")
    snapshot = adapter.get_snapshot(market.market_id)
    policy = adapter.get_resolution_policy(market.market_id)
    report = ResolutionGuard().evaluate(market, policy=policy, snapshot=snapshot)

    assert report.approved is True
    assert report.can_forecast is True
    assert report.manual_review_required is False
    assert report.status == ResolutionStatus.clear


def test_resolution_guard_flags_ambiguous_markets() -> None:
    adapter = PolymarketAdapter(backend_mode="surrogate")
    market = adapter.get_market("polymarket-ambiguous-geo-event")
    snapshot = adapter.get_snapshot(market.market_id)
    policy = adapter.get_resolution_policy(market.market_id)
    report = ResolutionGuard().evaluate(market, policy=policy, snapshot=snapshot)

    assert report.approved is False
    assert report.manual_review_required is True
    assert report.status in {ResolutionStatus.ambiguous, ResolutionStatus.manual_review}
    assert report.ambiguity_flags


def test_resolution_guard_blocks_missing_policy_and_surfaces_completeness() -> None:
    adapter = PolymarketAdapter(backend_mode="surrogate")
    market = adapter.get_market("polymarket-fed-cut-q3-2026")
    market = market.model_copy(update={"resolution_source": "", "question": "Will the market resolve?"})

    report = ResolutionGuard().evaluate(market, policy=None, snapshot=None)
    surface = describe_resolution_policy_surface(market)

    assert report.approved is False
    assert report.can_forecast is False
    assert report.no_trade is True
    assert report.manual_review_required is True
    assert "missing_resolution_policy" in report.reasons
    assert report.official_source_url == market.source_url
    assert report.required_fields_count >= 1
    assert report.present_fields_count == 0
    assert "official_source" in report.missing_fields
    assert report.summary
    assert surface.policy_complete is False
    assert surface.no_trade is True
    assert surface.policy_completeness_score < 1.0
    assert surface.policy_coherent is False
    assert surface.official_source_url == market.source_url
    assert surface.summary
    assert "missing_official_source" in surface.completeness_flags or "missing_source_url" in surface.completeness_flags


def test_resolution_guard_surfaces_next_review_at_as_utc_iso() -> None:
    adapter = PolymarketAdapter(backend_mode="surrogate")
    market = adapter.get_market("polymarket-fed-cut-q3-2026")
    policy = adapter.get_resolution_policy(market.market_id).model_copy(
        update={"next_review_at": datetime(2026, 4, 8, 2, 0, tzinfo=timezone(timedelta(hours=2)))}
    )

    report = ResolutionGuard().evaluate(market, policy=policy, snapshot=adapter.get_snapshot(market.market_id))
    surface = describe_resolution_policy_surface(market, policy=policy)

    assert report.next_review_at == "2026-04-08T00:00:00+00:00"
    assert surface.next_review_at == "2026-04-08T00:00:00+00:00"
    assert surface.metadata["next_review_at"] == "2026-04-08T00:00:00+00:00"
    assert surface.content_hash


def test_resolution_policy_completeness_report_tracks_rates(tmp_path: Path) -> None:
    adapter = PolymarketAdapter(backend_mode="surrogate")
    clear_market = adapter.get_market("polymarket-fed-cut-q3-2026")
    ambiguous_market = adapter.get_market("polymarket-ambiguous-geo-event")

    report = build_resolution_policy_completeness_report([clear_market, ambiguous_market])

    assert isinstance(report, ResolutionPolicyCompletenessReport)
    assert report.market_count == 2
    assert report.policy_count == 2
    assert report.complete_count <= report.market_count
    assert report.no_trade_count >= 1
    assert 0.0 <= report.complete_rate <= 1.0
    assert 0.0 <= report.coherent_rate <= 1.0
    assert 0.0 <= report.manual_review_rate <= 1.0
    assert 0.0 <= report.ambiguous_rate <= 1.0
    assert 0.0 <= report.unavailable_rate <= 1.0
    assert report.summary
    assert report.content_hash
    assert report.surfaces
    assert report.surfaces[0].content_hash


def test_evidence_registry_and_policy_cache_roundtrip(tmp_path: Path) -> None:
    adapter = PolymarketAdapter(backend_mode="surrogate")
    market = adapter.get_market("polymarket-fed-cut-q3-2026")
    collector = ResearchCollector()
    evidence = collector.from_notes(market_id=market.market_id, notes=["Bullish note for testing"], run_id="run_1")[0]
    evidence.metadata["run_id"] = "run_1"

    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    registry = EvidenceRegistry(paths)
    registry.add(evidence)
    index = registry.load_index()

    assert registry.get(evidence.evidence_id) is not None
    assert registry.list_by_market(market.market_id)
    assert registry.list_by_run("run_1")
    assert registry.list_by_provenance_ref("run:run_1") == []
    assert index.entries
    assert index.entries[0].artifact_refs
    assert index.entries[0].stored_at is not None
    assert index.entries[0].content_hash is not None
    assert "stored_at" in registry.get(evidence.evidence_id).metadata
    assert "artifact_refs" in registry.get(evidence.evidence_id).metadata

    cache = ResolutionPolicyCache(paths)
    policy = adapter.get_resolution_policy(market.market_id)
    cache.set(policy)
    assert cache.get(market.market_id) is not None


def test_evidence_registry_indexes_source_kind_and_classification(tmp_path: Path) -> None:
    adapter = PolymarketAdapter(backend_mode="surrogate")
    market = adapter.get_market("polymarket-fed-cut-q3-2026")
    collector = ResearchCollector()
    evidence = collector.from_notes(market_id=market.market_id, notes=["Bullish note for testing"], run_id="run_2")[0]
    evidence.metadata["run_id"] = "run_2"
    evidence.metadata["classification"] = "signal-only"
    evidence.metadata["source_type"] = "twitter_watcher_sidecar"
    evidence.provenance_refs.append("tweet:t-1")

    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    registry = EvidenceRegistry(paths)
    registry.add(evidence)
    index = registry.load_index()

    assert registry.list_by_source_kind(evidence.source_kind.value)
    assert registry.list_by_provenance_ref("tweet:t-1")
    assert registry.list_signal_only()
    assert index.entries[0].artifact_refs
    assert "artifact_refs" in registry.get(evidence.evidence_id).metadata
