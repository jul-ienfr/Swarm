from __future__ import annotations

from datetime import datetime, timezone

import pytest

from prediction_markets.models import EvidencePacket, SourceKind, VenueName
from prediction_markets.research import ResearchCollector, ResearchFinding
from prediction_markets.research import (
    ResearchAbstentionPolicy,
    ResearchBaseRateSummary,
    ResearchPipelineSurface,
    ResearchRetrievalSummary,
    ResearchSynthesis,
    build_research_abstention_metrics,
)
from prediction_markets.research_asof import (
    AbstentionQualityReport,
    AsOfEvidenceSet,
    AsOfBenchmarkReport,
    AsOfBenchmarkSuite,
    CalibrationCurveReport,
    BaseRateResearcher,
    ForecastUpliftComparisonReport,
    build_asof_evidence_set,
    build_asof_benchmark,
    build_abstention_quality_report,
    build_calibration_curve_report,
    build_as_of_benchmark_suite,
    build_calibration_snapshot,
    compare_forecast_only_vs_enriched,
    build_forecast_evaluation,
    build_research_report,
)


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def test_asof_evidence_set_filters_future_findings_and_roundtrips(tmp_path) -> None:
    cutoff = _utc("2026-04-08T12:00:00Z")
    findings = [
        ResearchFinding(
            claim="Bullish catalyst arrived",
            stance="bullish",
            source_kind=SourceKind.official,
            source_url="https://example.com/a",
            published_at=_utc("2026-04-08T10:00:00Z"),
            metadata={"theme": "macro"},
        ),
        ResearchFinding(
            claim="Future update should be ignored",
            stance="bearish",
            source_kind=SourceKind.news,
            source_url="https://example.com/b",
            published_at=_utc("2026-04-08T14:00:00Z"),
            metadata={"theme": "macro"},
        ),
    ]

    evidence_set = build_asof_evidence_set(
        findings,
        market_id="market_asof",
        cutoff_at=cutoff,
        venue=VenueName.polymarket,
        run_id="run_asof",
    )

    path = evidence_set.persist(tmp_path / "asof.json")
    loaded = AsOfEvidenceSet.load(path)

    assert loaded.evidence_set_id == evidence_set.evidence_set_id
    assert loaded.cutoff_at == cutoff
    assert loaded.evidence_refs == evidence_set.evidence_refs
    assert loaded.metadata["selected_count"] == 1
    assert loaded.metadata["discarded_future_count"] == 1
    assert loaded.freshness_summary["finding_count"] == 1
    assert loaded.provenance_summary["source_kinds"] == ["official"]
    assert len(loaded.evidence_packets) == 1
    assert loaded.evidence_packets[0].claim == "Bullish catalyst arrived"


def test_asof_evidence_set_propagates_provenance_bundle_hashes() -> None:
    cutoff = _utc("2026-04-08T12:00:00Z")
    collector = ResearchCollector(venue=VenueName.polymarket)
    bridge = collector.bridge_bundle(
        ["Bullish catalyst arrived"],
        market_id="market_asof_bundle",
        run_id="run_asof_bundle",
        social_context_refs=["ctx-1"],
    )
    evidence = collector.from_notes(
        market_id="market_asof_bundle",
        notes=["Bullish catalyst arrived"],
        run_id="run_asof_bundle",
    )[0]
    evidence = EvidencePacket.model_validate(
        {
            **evidence.model_dump(mode="json"),
            "metadata": {
                **evidence.metadata,
                "provenance_bundle_content_hash": bridge.provenance_bundle.content_hash if bridge.provenance_bundle is not None else "",
            },
        }
    )

    evidence_set = build_asof_evidence_set(
        [evidence],
        market_id="market_asof_bundle",
        cutoff_at=cutoff,
        venue=VenueName.polymarket,
        run_id="run_asof_bundle",
    )

    assert evidence_set.provenance_summary["provenance_bundle_content_hashes"] == [
        bridge.provenance_bundle.content_hash if bridge.provenance_bundle is not None else ""
    ]
    assert evidence_set.provenance_summary["provenance_bundle_count"] == 1


def test_base_rate_researcher_builds_report_with_estimated_base_rate(tmp_path) -> None:
    researcher = BaseRateResearcher()
    records = [
        build_forecast_evaluation(
            question_id="q1",
            market_id="m1",
            forecast_probability=0.9,
            resolved_outcome=True,
            cutoff_at=_utc("2026-04-08T10:00:00Z"),
            market_family="macro",
            horizon_bucket="30d",
        ),
        build_forecast_evaluation(
            question_id="q2",
            market_id="m2",
            forecast_probability=0.8,
            resolved_outcome=True,
            cutoff_at=_utc("2026-04-08T10:30:00Z"),
            market_family="macro",
            horizon_bucket="30d",
        ),
        build_forecast_evaluation(
            question_id="q3",
            market_id="m3",
            forecast_probability=0.2,
            resolved_outcome=False,
            cutoff_at=_utc("2026-04-08T11:00:00Z"),
            market_family="macro",
            horizon_bucket="30d",
        ),
    ]
    for record in records:
        researcher.ingest(record)

    findings = [
        ResearchFinding(
            claim="Rate cut probability is rising",
            stance="bullish",
            source_kind=SourceKind.official,
            published_at=_utc("2026-04-08T09:30:00Z"),
            metadata={"theme": "macro"},
        ),
        ResearchFinding(
            claim="Inflation risk remains",
            stance="bearish",
            source_kind=SourceKind.news,
            published_at=_utc("2026-04-08T09:45:00Z"),
            metadata={"theme": "macro"},
        ),
    ]

    report = build_research_report(
        findings,
        market_id="market_report",
        as_of=_utc("2026-04-08T12:00:00Z"),
        venue=VenueName.polymarket,
        researcher=researcher,
        market_family="macro",
        horizon_bucket="30d",
    )

    path = report.persist(tmp_path / "report.json")
    loaded = report.load(path)

    assert loaded.report_id == report.report_id
    assert loaded.base_rates["estimated_base_rate"] == pytest.approx(0.6)
    assert loaded.facts
    assert loaded.theses
    assert loaded.objections
    assert loaded.summary == report.summary
    assert loaded.summary.startswith("2 findings;")
    assert loaded.key_factors == loaded.theses
    assert loaded.counterarguments == loaded.objections
    assert loaded.supporting_evidence_refs
    assert loaded.key_factors
    assert loaded.open_questions
    assert loaded.metadata["finding_count"] == 2
    assert loaded.metadata["market_family"] == "macro"
    assert loaded.evidence_set_id is not None
    assert loaded.as_of_cutoff_at is not None
    assert loaded.content_hash


def test_research_abstention_metrics_include_pipeline_and_retrieval_signals() -> None:
    pipeline = ResearchPipelineSurface(
        market_id="market_research",
        venue=VenueName.polymarket,
        run_id="run_research",
        pipeline_summary="research pipeline summary",
        base_rates=ResearchBaseRateSummary(
            market_id="market_research",
            venue=VenueName.polymarket,
            run_id="run_research",
            finding_count=3,
            bullish_share=0.5,
            bearish_share=0.25,
            neutral_share=0.25,
            bullish_weight_share=0.6,
            bearish_weight_share=0.2,
            neutral_weight_share=0.2,
            estimated_base_rate_yes=0.63,
            signal_dispersion=0.41,
            source_kind_counts={"official": 1, "news": 1},
        ),
        retrieval=ResearchRetrievalSummary(
            market_id="market_research",
            venue=VenueName.polymarket,
            run_id="run_research",
            retrieval_policy="research_inputs",
            input_count=4,
            normalized_count=3,
            deduplicated_count=2,
            duplicate_count=1,
            duplicate_rate=0.25,
            evidence_count=2,
            external_url_count=1,
            external_url_rate=0.5,
            source_kind_counts={"official": 1, "news": 1},
            retrieval_status="ready",
        ),
        synthesis=ResearchSynthesis(
            market_id="market_research",
            venue=VenueName.polymarket,
            run_id="run_research",
            finding_count=3,
            evidence_count=2,
            bullish_count=2,
            bearish_count=1,
            neutral_count=0,
            bullish_weight=0.65,
            bearish_weight=0.2,
            neutral_weight=0.15,
            net_bias=0.45,
            dominant_stance="bullish",
            average_confidence=0.61,
            average_freshness=0.82,
            average_credibility=0.78,
            average_evidence_weight=0.51,
            themes=["macro"],
            top_claims=["Claim A"],
            summary="Synthesis summary",
        ),
        abstention_policy=ResearchAbstentionPolicy(
            market_id="market_research",
            venue=VenueName.polymarket,
            run_id="run_research",
            abstain=True,
            status="hold",
            reason_codes=["insufficient_evidence", "stale_inputs"],
            finding_count=3,
            evidence_count=2,
            duplicate_rate=0.25,
            completeness_score=0.67,
            average_confidence=0.59,
            average_evidence_weight=0.48,
            net_bias=0.1,
            signal_strength=0.43,
            abstention_score=0.72,
            applied=True,
        ),
    )

    metrics = build_research_abstention_metrics(pipeline)

    assert metrics["pipeline_version"] == "research_pipeline_v1"
    assert metrics["policy_scope"] == "research_only"
    assert metrics["retrieval_policy"] == "research_inputs"
    assert metrics["retrieval_status"] == "ready"
    assert metrics["retrieval_input_count"] == 4
    assert metrics["retrieval_deduplicated_count"] == 2
    assert metrics["retrieval_duplicate_rate"] == pytest.approx(0.25)
    assert metrics["estimated_base_rate_yes"] == pytest.approx(0.63)
    assert metrics["base_rate_bullish_share"] == pytest.approx(0.5)
    assert metrics["base_rate_bearish_weight_share"] == pytest.approx(0.2)
    assert metrics["dominant_stance"] == "bullish"
    assert metrics["reason_codes"] == ["insufficient_evidence", "stale_inputs"]
    assert metrics["retrieval_source_kind_counts"] == {"news": 1, "official": 1}
    assert metrics["pipeline_summary"] == "research pipeline summary"


def test_forecast_evaluation_and_calibration_snapshot_are_deterministic(tmp_path) -> None:
    records = [
        build_forecast_evaluation(
            question_id="q1",
            market_id="m1",
            forecast_probability=0.9,
            resolved_outcome=True,
            cutoff_at=_utc("2026-04-08T09:00:00Z"),
            market_family="macro",
            horizon_bucket="30d",
        ),
        build_forecast_evaluation(
            question_id="q2",
            market_id="m2",
            forecast_probability=0.8,
            resolved_outcome=True,
            cutoff_at=_utc("2026-04-08T09:30:00Z"),
            market_family="macro",
            horizon_bucket="30d",
        ),
        build_forecast_evaluation(
            question_id="q3",
            market_id="m3",
            forecast_probability=0.2,
            resolved_outcome=False,
            cutoff_at=_utc("2026-04-08T10:00:00Z"),
            market_family="macro",
            horizon_bucket="30d",
        ),
        build_forecast_evaluation(
            question_id="q4",
            market_id="m4",
            forecast_probability=0.0,
            resolved_outcome=False,
            cutoff_at=_utc("2026-04-08T10:30:00Z"),
            abstain_flag=True,
            market_family="macro",
            horizon_bucket="30d",
        ),
    ]

    snapshot = build_calibration_snapshot(
        records,
        model_family="baseline",
        market_family="macro",
        horizon_bucket="30d",
        window_start=_utc("2026-04-08T00:00:00Z"),
        window_end=_utc("2026-04-08T23:59:59Z"),
    )
    path = snapshot.persist(tmp_path / "calibration.json")
    loaded = snapshot.load(path)

    assert records[0].brier_score == pytest.approx(0.01)
    assert records[0].log_loss > 0.0
    assert records[0].ece_bucket.startswith("decile_")
    assert loaded.evaluation_count == 4
    assert loaded.abstain_count == 1
    assert loaded.coverage == pytest.approx(0.75)
    assert loaded.abstention_coverage == pytest.approx(0.75)
    assert loaded.ece == pytest.approx(0.125)
    assert loaded.sharpness > 0.0
    assert loaded.mean_market_baseline_delta == pytest.approx(-0.025)
    assert loaded.mean_market_baseline_delta_bps == pytest.approx(-250.0)
    assert loaded.content_hash


def test_asof_benchmark_filters_future_inputs_and_is_deterministic(tmp_path) -> None:
    cutoff = _utc("2026-04-08T12:00:00Z")
    findings = [
        ResearchFinding(
            claim="Bullish catalyst arrived",
            stance="bullish",
            source_kind=SourceKind.official,
            source_url="https://example.com/a",
            published_at=_utc("2026-04-08T10:00:00Z"),
            metadata={"theme": "macro"},
        ),
        ResearchFinding(
            claim="Future update should be ignored",
            stance="bearish",
            source_kind=SourceKind.news,
            source_url="https://example.com/b",
            published_at=_utc("2026-04-08T14:00:00Z"),
            metadata={"theme": "macro"},
        ),
    ]
    evaluations = [
        build_forecast_evaluation(
            question_id="q1",
            market_id="market_asof",
            forecast_probability=0.9,
            resolved_outcome=True,
            cutoff_at=_utc("2026-04-08T09:00:00Z"),
            market_family="macro",
            horizon_bucket="30d",
        ),
        build_forecast_evaluation(
            question_id="q2",
            market_id="market_asof",
            forecast_probability=0.1,
            resolved_outcome=False,
            cutoff_at=_utc("2026-04-08T14:00:00Z"),
            market_family="macro",
            horizon_bucket="30d",
        ),
    ]

    benchmark_a = build_asof_benchmark(
        findings,
        evaluations,
        market_id="market_asof",
        as_of=cutoff,
        venue=VenueName.polymarket,
        market_family="macro",
        horizon_bucket="30d",
    )
    benchmark_b = build_asof_benchmark(
        list(reversed(findings)),
        list(reversed(evaluations)),
        market_id="market_asof",
        as_of=cutoff,
        venue=VenueName.polymarket,
        market_family="macro",
        horizon_bucket="30d",
    )

    path = benchmark_a.persist(tmp_path / "benchmark.json")
    loaded = AsOfBenchmarkReport.load(path)

    assert benchmark_a.content_hash == benchmark_b.content_hash
    assert benchmark_a.contamination_free is True
    assert benchmark_a.evidence_set.metadata["selected_count"] == 1
    assert benchmark_a.evidence_set.metadata["discarded_future_count"] == 1
    assert benchmark_a.excluded_future_evaluation_count == 1
    assert benchmark_a.calibration_snapshot is not None
    assert benchmark_a.calibration_snapshot.record_count == 1
    assert benchmark_a.calibration_snapshot.metadata["contamination_free"] is True
    assert benchmark_a.calibration_snapshot.metadata["excluded_future_record_count"] == 1
    assert benchmark_a.calibration_snapshot.abstention_coverage == pytest.approx(1.0)
    assert benchmark_a.calibration_snapshot.content_hash
    assert benchmark_a.stable_benchmark is True
    assert benchmark_a.benchmark_scope_hash
    assert loaded.content_hash == benchmark_a.content_hash
    assert loaded.metadata["contamination_free"] is True


def test_asof_benchmark_suite_excludes_invalid_cutoffs_deterministically() -> None:
    cutoff = _utc("2026-04-08T12:00:00Z")

    class LooseEvaluationRecord:
        def __init__(
            self,
            *,
            evaluation_id: str,
            question_id: str,
            market_id: str,
            cutoff_at,
            forecast_probability: float,
            resolved_outcome: bool,
            model_family: str,
            market_family: str,
            horizon_bucket: str,
        ) -> None:
            self.evaluation_id = evaluation_id
            self.question_id = question_id
            self.market_id = market_id
            self.cutoff_at = cutoff_at
            self.forecast_probability = forecast_probability
            self.resolved_outcome = resolved_outcome
            self.model_family = model_family
            self.market_family = market_family
            self.horizon_bucket = horizon_bucket

    evaluations = [
        build_forecast_evaluation(
            question_id="q1",
            market_id="market_asof",
            forecast_probability=0.9,
            resolved_outcome=True,
            cutoff_at=_utc("2026-04-08T09:00:00Z"),
            model_family="model_v1",
            market_family="macro",
            horizon_bucket="30d",
        ),
        LooseEvaluationRecord(
            evaluation_id="feval_invalid",
            question_id="q2",
            market_id="market_asof",
            cutoff_at="not-a-datetime",
            forecast_probability=0.4,
            resolved_outcome=False,
            model_family="model_v1",
            market_family="macro",
            horizon_bucket="30d",
        ),
        build_forecast_evaluation(
            question_id="q3",
            market_id="market_asof",
            forecast_probability=0.1,
            resolved_outcome=False,
            cutoff_at=_utc("2026-04-08T14:00:00Z"),
            model_family="model_v1",
            market_family="macro",
            horizon_bucket="30d",
        ),
    ]

    suite_a = build_as_of_benchmark_suite(
        [],
        evaluations,
        market_id="market_asof",
        as_of=cutoff,
        venue=VenueName.polymarket,
        market_family="macro",
        horizon_bucket="30d",
        metadata={"source": "unit-test"},
    )
    suite_b = build_as_of_benchmark_suite(
        [],
        list(reversed(evaluations)),
        market_id="market_asof",
        as_of=cutoff,
        venue=VenueName.polymarket,
        market_family="macro",
        horizon_bucket="30d",
        metadata={"source": "unit-test"},
    )

    assert suite_a.excluded_future_evaluation_count == 1
    assert suite_b.excluded_future_evaluation_count == 1
    assert suite_a.metadata["excluded_invalid_evaluation_count"] == 1
    assert suite_b.metadata["excluded_invalid_evaluation_count"] == 1
    assert suite_a.metadata["selected_evaluation_count"] == 1
    assert suite_b.metadata["selected_evaluation_count"] == 1
    assert suite_a.calibration_snapshot is None or suite_a.calibration_snapshot.record_count == 1


def test_asof_benchmark_includes_version_and_baseline_comparisons_without_future_contamination() -> None:
    cutoff = _utc("2026-04-08T12:00:00Z")
    findings = [
        ResearchFinding(
            claim="Bullish catalyst arrived",
            stance="bullish",
            source_kind=SourceKind.official,
            source_url="https://example.com/a",
            published_at=_utc("2026-04-08T10:00:00Z"),
            metadata={"theme": "macro"},
        )
    ]
    evaluations = [
        build_forecast_evaluation(
            question_id="q1",
            market_id="market_asof",
            forecast_probability=0.8,
            resolved_outcome=True,
            cutoff_at=_utc("2026-04-08T09:00:00Z"),
            model_family="model_v1",
            market_family="macro",
            horizon_bucket="30d",
        ),
        build_forecast_evaluation(
            question_id="q1",
            market_id="market_asof",
            forecast_probability=0.55,
            resolved_outcome=True,
            cutoff_at=_utc("2026-04-08T09:00:00Z"),
            model_family="model_v2",
            market_family="macro",
            horizon_bucket="30d",
        ),
        build_forecast_evaluation(
            question_id="q2",
            market_id="market_asof",
            forecast_probability=0.2,
            resolved_outcome=False,
            cutoff_at=_utc("2026-04-08T13:00:00Z"),
            model_family="model_v1",
            market_family="macro",
            horizon_bucket="30d",
        ),
        build_forecast_evaluation(
            question_id="q2",
            market_id="market_asof",
            forecast_probability=0.35,
            resolved_outcome=False,
            cutoff_at=_utc("2026-04-08T13:00:00Z"),
            model_family="model_v2",
            market_family="macro",
            horizon_bucket="30d",
        ),
    ]

    benchmark = build_asof_benchmark(
        findings,
        evaluations,
        market_id="market_asof",
        as_of=cutoff,
        venue=VenueName.polymarket,
        market_family="macro",
        horizon_bucket="30d",
    )

    assert benchmark.contamination_free is True
    assert benchmark.stable_benchmark is True
    assert benchmark.model_version_comparisons
    assert benchmark.baseline_comparisons
    assert all(report.metadata["contamination_free"] is True for report in benchmark.model_version_comparisons)
    assert all(report.metadata["contamination_free"] is True for report in benchmark.baseline_comparisons)
    assert all(report.metadata["as_of_cutoff_at"] == cutoff.isoformat() for report in benchmark.model_version_comparisons)
    assert all(report.metadata["as_of_cutoff_at"] == cutoff.isoformat() for report in benchmark.baseline_comparisons)
    assert all(report.aligned_pair_count == 1 for report in benchmark.model_version_comparisons)
    assert any(report.baseline_label == "simple_0.5" for report in benchmark.baseline_comparisons)
    assert any(report.baseline_label == "estimated_base_rate" for report in benchmark.baseline_comparisons)


def test_asof_benchmark_suite_wrapper_preserves_strict_cutoff_and_family_roles() -> None:
    cutoff = _utc("2026-04-08T12:00:00Z")
    findings = [
        ResearchFinding(
            claim="Bullish catalyst arrived",
            stance="bullish",
            source_kind=SourceKind.official,
            source_url="https://example.com/a",
            published_at=_utc("2026-04-08T10:00:00Z"),
            metadata={"theme": "macro"},
        ),
        ResearchFinding(
            claim="Future update should be ignored",
            stance="bearish",
            source_kind=SourceKind.news,
            source_url="https://example.com/b",
            published_at=_utc("2026-04-08T14:00:00Z"),
            metadata={"theme": "macro"},
        ),
    ]
    evaluations = [
        build_forecast_evaluation(
            question_id="q1",
            market_id="market_asof",
            forecast_probability=0.54,
            resolved_outcome=True,
            cutoff_at=_utc("2026-04-08T09:00:00Z"),
            model_family="market_only_model",
            market_family="macro",
            horizon_bucket="30d",
        ),
        build_forecast_evaluation(
            question_id="q1",
            market_id="market_asof",
            forecast_probability=0.68,
            resolved_outcome=True,
            cutoff_at=_utc("2026-04-08T09:00:00Z"),
            model_family="single_llm_model",
            market_family="macro",
            horizon_bucket="30d",
        ),
        build_forecast_evaluation(
            question_id="q1",
            market_id="market_asof",
            forecast_probability=0.77,
            resolved_outcome=True,
            cutoff_at=_utc("2026-04-08T09:00:00Z"),
            model_family="ensemble_model",
            market_family="macro",
            horizon_bucket="30d",
        ),
        build_forecast_evaluation(
            question_id="q1",
            market_id="market_asof",
            forecast_probability=0.73,
            resolved_outcome=True,
            cutoff_at=_utc("2026-04-08T09:00:00Z"),
            model_family="decision_packet_assisted_model",
            market_family="macro",
            horizon_bucket="30d",
        ),
        build_forecast_evaluation(
            question_id="q2",
            market_id="market_asof",
            forecast_probability=0.2,
            resolved_outcome=False,
            cutoff_at=_utc("2026-04-08T13:00:00Z"),
            model_family="ensemble_model",
            market_family="macro",
            horizon_bucket="30d",
        ),
    ]

    suite = build_as_of_benchmark_suite(
        findings,
        evaluations,
        market_id="market_asof",
        as_of=cutoff,
        venue=VenueName.polymarket,
        market_family="macro",
        horizon_bucket="30d",
        family_labels={
            "market_only_model": "market-only",
            "single_llm_model": "single-LLM",
            "ensemble_model": "ensemble",
            "decision_packet_assisted_model": "DecisionPacket-assisted",
        },
        metadata={"source": "unit-test"},
    )

    assert isinstance(suite, AsOfBenchmarkSuite)
    assert suite.contamination_free is True
    assert suite.excluded_future_finding_count == 1
    assert suite.excluded_future_evaluation_count == 1
    assert suite.evidence_set.metadata["selected_count"] == 1
    assert suite.research_report.summary.startswith("Research report for market_asof")
    assert {summary.family_role for summary in suite.family_summaries} == {
        "market-only",
        "single-LLM",
        "ensemble",
        "DecisionPacket-assisted",
    }
    assert suite.canonical_score_components["market_baseline_delta_bps"] == pytest.approx(
        suite.canonical_score_components["market_baseline_delta"] * 10000.0
    )
    assert suite.canonical_score_components["family_count"] == pytest.approx(4.0)
    assert len(suite.model_version_comparisons) == 6
    assert len(suite.baseline_comparisons) >= 4


def test_compare_forecast_only_vs_enriched_excludes_future_records_and_tracks_uplift() -> None:
    cutoff = _utc("2026-04-08T12:00:00Z")
    evaluations = [
        build_forecast_evaluation(
            question_id="q1",
            market_id="market_uplift",
            forecast_probability=0.73,
            resolved_outcome=True,
            cutoff_at=_utc("2026-04-08T09:00:00Z"),
            model_family="forecast_only_model",
            market_family="macro",
            horizon_bucket="30d",
            market_baseline_probability=0.55,
        ),
        build_forecast_evaluation(
            question_id="q2",
            market_id="market_uplift",
            forecast_probability=0.24,
            resolved_outcome=False,
            cutoff_at=_utc("2026-04-08T09:30:00Z"),
            model_family="forecast_only_model",
            market_family="macro",
            horizon_bucket="30d",
            market_baseline_probability=0.46,
        ),
        build_forecast_evaluation(
            question_id="q1",
            market_id="market_uplift",
            forecast_probability=0.88,
            resolved_outcome=True,
            cutoff_at=_utc("2026-04-08T09:00:00Z"),
            model_family="enriched_model",
            market_family="macro",
            horizon_bucket="30d",
            market_baseline_probability=0.55,
        ),
        build_forecast_evaluation(
            question_id="q2",
            market_id="market_uplift",
            forecast_probability=0.11,
            resolved_outcome=False,
            cutoff_at=_utc("2026-04-08T09:30:00Z"),
            model_family="enriched_model",
            market_family="macro",
            horizon_bucket="30d",
            market_baseline_probability=0.46,
        ),
        build_forecast_evaluation(
            question_id="q3",
            market_id="market_uplift",
            forecast_probability=0.61,
            resolved_outcome=True,
            cutoff_at=_utc("2026-04-08T15:00:00Z"),
            model_family="enriched_model",
            market_family="macro",
            horizon_bucket="30d",
            market_baseline_probability=0.53,
        ),
    ]

    uplift = compare_forecast_only_vs_enriched(
        evaluations,
        forecast_only_model_family="forecast_only_model",
        enriched_model_family="enriched_model",
        market_family="macro",
        horizon_bucket="30d",
        as_of=cutoff,
        metadata={"source": "unit-test"},
    )

    assert isinstance(uplift, ForecastUpliftComparisonReport)
    assert uplift.forecast_only_record_count == 2
    assert uplift.enriched_record_count == 2
    assert uplift.aligned_pair_count == 2
    assert uplift.brier_improvement > 0.0
    assert uplift.log_loss_improvement > 0.0
    assert uplift.metadata["as_of_cutoff_at"] == cutoff.isoformat()
    assert uplift.metadata["contamination_free"] is True
    assert uplift.metadata["stable_benchmark"] is True

    uplift_reordered = compare_forecast_only_vs_enriched(
        list(reversed(evaluations)),
        forecast_only_model_family="forecast_only_model",
        enriched_model_family="enriched_model",
        market_family="macro",
        horizon_bucket="30d",
        as_of=cutoff,
        metadata={"source": "unit-test"},
    )

    assert uplift_reordered.content_hash == uplift.content_hash
    assert uplift_reordered.comparison_scope_hash == uplift.comparison_scope_hash


def test_research_asof_exports_calibration_curve_and_abstention_quality_reports() -> None:
    cutoff = _utc("2026-04-08T12:00:00Z")
    evaluations = [
        build_forecast_evaluation(
            question_id="q1",
            market_id="market_asof",
            forecast_probability=0.81,
            resolved_outcome=True,
            cutoff_at=_utc("2026-04-08T09:00:00Z"),
            model_family="model_v1",
            market_family="macro",
            horizon_bucket="30d",
            metadata={"category": "macro-growth"},
        ),
        build_forecast_evaluation(
            question_id="q2",
            market_id="market_asof",
            forecast_probability=0.24,
            resolved_outcome=False,
            cutoff_at=_utc("2026-04-08T09:30:00Z"),
            model_family="model_v1",
            market_family="macro",
            horizon_bucket="30d",
            metadata={"category": "macro-growth"},
        ),
        build_forecast_evaluation(
            question_id="q3",
            market_id="market_asof",
            forecast_probability=0.55,
            resolved_outcome=True,
            cutoff_at=_utc("2026-04-08T10:00:00Z"),
            abstain_flag=True,
            model_family="model_v1",
            market_family="macro",
            horizon_bucket="30d",
            metadata={"category": "micro-liquidity"},
        ),
    ]

    curve = build_calibration_curve_report(
        evaluations,
        model_family="model_v1",
        market_family="macro",
        horizon_bucket="30d",
        as_of=cutoff,
        metadata={"source": "unit-test"},
    )
    abstention = build_abstention_quality_report(
        evaluations,
        model_family="model_v1",
        market_family="macro",
        as_of=cutoff,
        metadata={"source": "unit-test"},
    )

    assert isinstance(curve, CalibrationCurveReport)
    assert curve.record_count == 3
    assert curve.active_count == 2
    assert curve.abstain_rate == pytest.approx(1 / 3)
    assert curve.bucket_summaries
    assert curve.content_hash
    assert isinstance(abstention, AbstentionQualityReport)
    assert abstention.record_count == 3
    assert abstention.abstain_count == 1
    assert abstention.mean_abstention_margin_gap > 0.0
    assert abstention.content_hash
