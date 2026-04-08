from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from prediction_markets.forecast_evaluation import (
    AbstentionQualityReport,
    AsOfEvidenceSet,
    AsOfBenchmarkSuite,
    CalibrationBucketSummary,
    CalibrationCurveReport,
    CalibrationSnapshot,
    BenchmarkFamilySummary,
    CategoryHorizonPerformanceReport,
    CategoryHorizonPerformanceSummary,
    ForecastBaselineComparisonReport,
    ForecastEvaluationHarness,
    ForecastEvaluationRecord,
    ForecastUpliftComparisonReport,
    ResearchReport,
    build_abstention_quality_report,
    build_baseline_comparison_report,
    build_calibration_curve_report,
    build_category_horizon_performance_report,
    build_as_of_benchmark_suite,
    build_as_of_calibration_snapshot,
    build_forecast_uplift_comparison_report,
    build_model_version_comparison_report,
)
from prediction_markets.models import DecisionAction, EvidencePacket, ForecastPacket, SourceKind, VenueName


def _evidence(
    evidence_id: str,
    *,
    claim: str,
    observed_at: datetime,
    stance: str = "neutral",
    source_kind: SourceKind = SourceKind.manual,
) -> EvidencePacket:
    return EvidencePacket(
        evidence_id=evidence_id,
        market_id="pm_eval_1",
        venue=VenueName.polymarket,
        source_kind=source_kind,
        claim=claim,
        stance=stance,
        source_url=f"https://example.com/{evidence_id}",
        observed_at=observed_at,
        confidence=0.8,
        freshness_score=0.9,
        credibility_score=0.85,
        provenance_refs=[f"prov:{evidence_id}"],
        tags=["test", "evaluation"],
    )


def _forecast() -> ForecastPacket:
    return ForecastPacket(
        run_id="run_eval_1",
        market_id="pm_eval_1",
        venue=VenueName.polymarket,
        market_implied_probability=0.51,
        fair_probability=0.67,
        confidence_low=0.58,
        confidence_high=0.74,
        edge_bps=160.0,
        edge_after_fees_bps=92.0,
        recommendation_action=DecisionAction.bet,
        rationale="Structured forecast for evaluation testing.",
        evidence_refs=["evid_a", "evid_b"],
        market_context_refs=["ctx_market_1"],
        social_context_refs=["ctx_social_1"],
        model_used="demo-model",
    )


def test_forecast_evaluation_record_evaluate_and_roundtrip() -> None:
    record = ForecastEvaluationRecord.evaluate(
        question_id="q_eval_1",
        market_id="pm_eval_1",
        forecast_probability=0.72,
        resolved_outcome=True,
        venue=VenueName.polymarket,
        market_baseline_probability=0.55,
        model_family="demo-model",
        market_family="macro",
        horizon_bucket="30d",
        evidence_refs=["e1", "e1", "e2"],
    )

    assert record.evaluation_id.startswith("feval_")
    assert record.brier_score == pytest.approx((0.72 - 1.0) ** 2)
    assert record.log_loss > 0.0
    assert record.ece_bucket == "0.7-0.8"
    assert record.evidence_refs == ["e1", "e2"]
    assert record.market_baseline_delta == pytest.approx(0.17)
    assert record.market_baseline_delta_bps == pytest.approx(1700.0)

    encoded = record.model_dump_json()
    decoded = ForecastEvaluationRecord.model_validate_json(encoded)
    assert decoded.evaluation_id == record.evaluation_id
    assert decoded.forecast_probability == pytest.approx(0.72)
    assert decoded.resolved_outcome is True


def test_as_of_evidence_set_filters_and_summarizes() -> None:
    cutoff = datetime(2026, 4, 8, 0, 0, tzinfo=timezone.utc)
    evidence = [
        _evidence("e1", claim="Bullish catalyst", observed_at=cutoff - timedelta(hours=3), stance="bullish"),
        _evidence("e2", claim="Bearish risk", observed_at=cutoff - timedelta(minutes=10), stance="bearish"),
        _evidence("e3", claim="Too late", observed_at=cutoff + timedelta(minutes=5), stance="neutral"),
    ]

    evidence_set = AsOfEvidenceSet.from_evidence(
        evidence,
        market_id="pm_eval_1",
        cutoff_at=cutoff,
        retrieval_policy="as_of_strict",
    )

    assert evidence_set.evidence_refs == ["e1", "e2"]
    assert evidence_set.retrieval_policy == "as_of_strict"
    assert evidence_set.freshness_summary["count"] == 2
    assert evidence_set.provenance_summary["source_kind_counts"].get("bullish", 0) == 0
    assert evidence_set.provenance_summary["source_kind_counts"]["manual"] == 2


def test_calibration_snapshot_from_records_computes_summary() -> None:
    records = [
        ForecastEvaluationRecord.evaluate(
            question_id="q1",
            market_id="pm_eval_1",
            forecast_probability=0.8,
            resolved_outcome=True,
            market_baseline_probability=0.55,
            model_family="demo-model",
            market_family="macro",
            horizon_bucket="30d",
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q2",
            market_id="pm_eval_2",
            forecast_probability=0.25,
            resolved_outcome=False,
            market_baseline_probability=0.45,
            model_family="demo-model",
            market_family="macro",
            horizon_bucket="30d",
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q3",
            market_id="pm_eval_3",
            forecast_probability=0.61,
            resolved_outcome=True,
            abstain_flag=True,
            market_baseline_probability=0.5,
            model_family="demo-model",
            market_family="macro",
            horizon_bucket="30d",
        ),
    ]

    snapshot = CalibrationSnapshot.from_records(
        records,
        model_family="demo-model",
        market_family="macro",
        horizon_bucket="30d",
    )

    assert snapshot.record_count == 3
    assert snapshot.coverage == pytest.approx(2 / 3)
    assert snapshot.abstain_rate == pytest.approx(1 / 3)
    assert snapshot.abstention_coverage == pytest.approx(2 / 3)
    assert snapshot.mean_brier_score > 0.0
    assert snapshot.mean_log_loss > 0.0
    assert snapshot.sharpness > 0.0
    assert snapshot.ece >= 0.0
    assert snapshot.mean_market_baseline_delta == pytest.approx(0.053333, abs=1e-6)
    assert snapshot.mean_market_baseline_delta_bps == pytest.approx(533.33, abs=1e-2)
    assert snapshot.evaluation_refs == [record.evaluation_id for record in records]
    assert snapshot.content_hash
    assert snapshot.bucket_summaries
    assert isinstance(snapshot.bucket_summaries[0], CalibrationBucketSummary)


def test_calibration_snapshot_from_records_as_of_counts_invalid_and_future_cutoffs_separately() -> None:
    cutoff = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)

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

    records = [
        ForecastEvaluationRecord.evaluate(
            question_id="q1",
            market_id="m1",
            forecast_probability=0.7,
            resolved_outcome=True,
            cutoff_at=datetime(2026, 4, 8, 9, 0, tzinfo=timezone.utc),
            model_family="baseline",
            market_family="macro",
            horizon_bucket="30d",
        ),
        LooseEvaluationRecord(
            evaluation_id="feval_invalid",
            question_id="q2",
            market_id="m1",
            cutoff_at="not-a-datetime",
            forecast_probability=0.4,
            resolved_outcome=False,
            model_family="baseline",
            market_family="macro",
            horizon_bucket="30d",
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q3",
            market_id="m1",
            forecast_probability=0.2,
            resolved_outcome=False,
            cutoff_at=datetime(2026, 4, 8, 14, 0, tzinfo=timezone.utc),
            model_family="baseline",
            market_family="macro",
            horizon_bucket="30d",
        ),
    ]

    snapshot = CalibrationSnapshot.from_records_as_of(
        records,
        as_of=cutoff,
        model_family="baseline",
        market_family="macro",
        horizon_bucket="30d",
    )

    assert snapshot.record_count == 1
    assert snapshot.metadata["included_record_count"] == 1
    assert snapshot.metadata["excluded_invalid_record_count"] == 1
    assert snapshot.metadata["excluded_future_record_count"] == 1
    assert snapshot.abstention_coverage == pytest.approx(1.0)
    assert snapshot.content_hash


def test_calibration_curve_report_and_bucket_summaries_are_stable() -> None:
    cutoff = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    records = [
        ForecastEvaluationRecord.evaluate(
            question_id="q1",
            market_id="pm_curve_1",
            forecast_probability=0.81,
            resolved_outcome=True,
            cutoff_at=cutoff,
            market_baseline_probability=0.52,
            model_family="demo-model",
            market_family="macro",
            horizon_bucket="30d",
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q2",
            market_id="pm_curve_2",
            forecast_probability=0.27,
            resolved_outcome=False,
            cutoff_at=cutoff,
            market_baseline_probability=0.44,
            model_family="demo-model",
            market_family="macro",
            horizon_bucket="30d",
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q3",
            market_id="pm_curve_3",
            forecast_probability=0.55,
            resolved_outcome=True,
            abstain_flag=True,
            cutoff_at=cutoff,
            market_baseline_probability=0.49,
            model_family="demo-model",
            market_family="macro",
            horizon_bucket="30d",
        ),
    ]

    report_a = build_calibration_curve_report(
        records,
        model_family="demo-model",
        market_family="macro",
        horizon_bucket="30d",
        bucket_count=10,
        as_of=cutoff,
        metadata={"source": "unit-test"},
    )
    report_b = build_calibration_curve_report(
        list(reversed(records)),
        model_family="demo-model",
        market_family="macro",
        horizon_bucket="30d",
        bucket_count=10,
        as_of=cutoff,
        metadata={"source": "unit-test"},
    )

    assert isinstance(report_a, CalibrationCurveReport)
    assert report_a.record_count == 3
    assert report_a.active_count == 2
    assert report_a.abstain_count == 1
    assert report_a.active_coverage == pytest.approx(2 / 3)
    assert report_a.abstention_coverage == pytest.approx(2 / 3)
    assert report_a.abstain_rate == pytest.approx(1 / 3)
    assert report_a.mean_ece >= 0.0
    assert report_a.mean_sharpness > 0.0
    assert report_a.bucket_summaries
    assert all(isinstance(bucket, CalibrationBucketSummary) for bucket in report_a.bucket_summaries)
    assert report_a.content_hash == report_b.content_hash
    assert report_a.bucket_summaries[0].content_hash


def test_category_horizon_performance_and_abstention_quality_reports_are_exposed() -> None:
    records = [
        ForecastEvaluationRecord.evaluate(
            question_id="q1",
            market_id="pm_segment_1",
            forecast_probability=0.91,
            resolved_outcome=True,
            market_baseline_probability=0.5,
            model_family="demo-model",
            market_family="macro",
            horizon_bucket="30d",
            metadata={"category": "macro-growth"},
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q2",
            market_id="pm_segment_2",
            forecast_probability=0.17,
            resolved_outcome=False,
            market_baseline_probability=0.5,
            model_family="demo-model",
            market_family="macro",
            horizon_bucket="30d",
            metadata={"category": "macro-growth"},
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q3",
            market_id="pm_segment_3",
            forecast_probability=0.53,
            resolved_outcome=True,
            abstain_flag=True,
            market_baseline_probability=0.5,
            model_family="demo-model",
            market_family="macro",
            horizon_bucket="90d",
            metadata={"category": "micro-liquidity"},
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q4",
            market_id="pm_segment_4",
            forecast_probability=0.48,
            resolved_outcome=False,
            abstain_flag=True,
            market_baseline_probability=0.5,
            model_family="demo-model",
            market_family="macro",
            horizon_bucket="90d",
            metadata={"category": "micro-liquidity"},
        ),
    ]

    performance = build_category_horizon_performance_report(records, metadata={"source": "unit-test"})
    abstention = build_abstention_quality_report(records, model_family="demo-model", market_family="macro", metadata={"source": "unit-test"})

    assert isinstance(performance, CategoryHorizonPerformanceReport)
    assert performance.segment_count == 2
    assert performance.record_count == 4
    assert performance.segments[0].category == "macro-growth"
    assert any(segment.horizon_bucket == "90d" for segment in performance.segments)
    assert any(segment.mean_brier_score >= 0.0 for segment in performance.segments)
    assert performance.content_hash

    assert isinstance(abstention, AbstentionQualityReport)
    assert abstention.record_count == 4
    assert abstention.active_count == 2
    assert abstention.abstain_count == 2
    assert abstention.mean_abstention_brier_gap > 0.0
    assert abstention.mean_abstention_margin_gap > 0.0
    assert abstention.content_hash


def test_model_version_comparison_is_stable_and_aligns_same_dataset(tmp_path) -> None:
    cutoff = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    records = [
        ForecastEvaluationRecord.evaluate(
            question_id="q1",
            market_id="pm_eval_1",
            forecast_probability=0.82,
            resolved_outcome=True,
            cutoff_at=cutoff,
            model_family="model_v1",
            market_family="macro",
            horizon_bucket="30d",
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q2",
            market_id="pm_eval_2",
            forecast_probability=0.24,
            resolved_outcome=False,
            cutoff_at=cutoff,
            model_family="model_v1",
            market_family="macro",
            horizon_bucket="30d",
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q1",
            market_id="pm_eval_1",
            forecast_probability=0.58,
            resolved_outcome=True,
            cutoff_at=cutoff,
            model_family="model_v2",
            market_family="macro",
            horizon_bucket="30d",
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q2",
            market_id="pm_eval_2",
            forecast_probability=0.41,
            resolved_outcome=False,
            cutoff_at=cutoff,
            model_family="model_v2",
            market_family="macro",
            horizon_bucket="30d",
        ),
    ]

    report_a = build_model_version_comparison_report(
        records,
        left_model_family="model_v1",
        right_model_family="model_v2",
        market_family="macro",
        horizon_bucket="30d",
        as_of=cutoff,
        metadata={"source": "unit-test"},
    )
    report_b = build_model_version_comparison_report(
        list(reversed(records)),
        left_model_family="model_v1",
        right_model_family="model_v2",
        market_family="macro",
        horizon_bucket="30d",
        as_of=cutoff,
        metadata={"source": "unit-test"},
    )

    assert report_a.aligned_pair_count == 2
    assert report_a.left_evaluation_count == 2
    assert report_a.right_evaluation_count == 2
    assert report_a.left_mean_brier_score < report_a.right_mean_brier_score
    assert report_a.left_win_count == 2
    assert report_a.right_win_count == 0
    assert report_a.tie_count == 0
    assert report_a.comparison_scope_hash == report_b.comparison_scope_hash
    assert report_a.content_hash == report_b.content_hash
    assert report_a.metadata["contamination_free"] is True
    assert report_a.metadata["stable_benchmark"] is True
    assert report_a.comparison_pairs[0].comparison_key

    persisted = report_a.persist(tmp_path / "model_version_comparison.json")
    loaded = type(report_a).load(persisted)
    assert loaded.content_hash == report_a.content_hash
    assert loaded.aligned_pair_count == report_a.aligned_pair_count
    assert loaded.left_win_count == report_a.left_win_count


def test_baseline_comparison_reports_against_simple_and_reference_baselines(tmp_path) -> None:
    cutoff = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    records = [
        ForecastEvaluationRecord.evaluate(
            question_id="q1",
            market_id="pm_eval_1",
            forecast_probability=0.74,
            resolved_outcome=True,
            cutoff_at=cutoff,
            model_family="model_v1",
            market_family="macro",
            horizon_bucket="30d",
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q2",
            market_id="pm_eval_2",
            forecast_probability=0.31,
            resolved_outcome=False,
            cutoff_at=cutoff,
            model_family="model_v1",
            market_family="macro",
            horizon_bucket="30d",
        ),
    ]

    simple = build_baseline_comparison_report(
        records,
        model_family="model_v1",
        market_family="macro",
        horizon_bucket="30d",
        baseline_probability=0.5,
        baseline_label="simple_0.5",
        as_of=cutoff,
        metadata={"source": "unit-test"},
    )
    reference = build_baseline_comparison_report(
        records,
        model_family="model_v1",
        market_family="macro",
        horizon_bucket="30d",
        baseline_probability=0.62,
        baseline_label="external_reference",
        as_of=cutoff,
        metadata={"source": "unit-test"},
    )

    assert simple.record_count == 2
    assert simple.model_win_count == 2
    assert simple.baseline_win_count == 0
    assert simple.baseline_probability == pytest.approx(0.5)
    assert simple.metadata["contamination_free"] is True
    assert simple.metadata["stable_benchmark"] is True
    assert simple.comparison_scope_hash
    assert simple.content_hash
    assert reference.baseline_label == "external_reference"
    assert reference.baseline_probability == pytest.approx(0.62)
    assert reference.record_count == 2
    assert reference.content_hash != simple.content_hash

    persisted = simple.persist(tmp_path / "baseline_comparison.json")
    loaded = type(simple).load(persisted)
    assert loaded.content_hash == simple.content_hash
    assert loaded.record_count == simple.record_count
    assert loaded.model_win_count == simple.model_win_count


def test_baseline_comparison_excludes_invalid_or_future_cutoffs_and_is_stable() -> None:
    cutoff = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    records = [
        ForecastEvaluationRecord.evaluate(
            question_id="q1",
            market_id="pm_eval_1",
            forecast_probability=0.74,
            resolved_outcome=True,
            cutoff_at=cutoff - timedelta(hours=3),
            model_family="model_v1",
            market_family="macro",
            horizon_bucket="30d",
        ),
        {
            "evaluation_id": "feval_invalid_1",
            "question_id": "q2",
            "market_id": "pm_eval_2",
            "venue": VenueName.polymarket,
            "cutoff_at": "not-a-datetime",
            "forecast_probability": 0.42,
            "resolved_outcome": False,
            "model_family": "model_v1",
            "market_family": "macro",
            "horizon_bucket": "30d",
        },
        ForecastEvaluationRecord.evaluate(
            question_id="q3",
            market_id="pm_eval_3",
            forecast_probability=0.31,
            resolved_outcome=False,
            cutoff_at=cutoff + timedelta(hours=3),
            model_family="model_v1",
            market_family="macro",
            horizon_bucket="30d",
        ),
    ]

    report_a = build_baseline_comparison_report(
        records,
        model_family="model_v1",
        market_family="macro",
        horizon_bucket="30d",
        baseline_probability=0.5,
        baseline_label="simple_0.5",
        as_of=cutoff,
        metadata={"source": "unit-test"},
    )
    report_b = build_baseline_comparison_report(
        list(reversed(records)),
        model_family="model_v1",
        market_family="macro",
        horizon_bucket="30d",
        baseline_probability=0.5,
        baseline_label="simple_0.5",
        as_of=cutoff,
        metadata={"source": "unit-test"},
    )

    assert report_a.record_count == 1
    assert report_a.comparison_pairs[0].cutoff_at == cutoff - timedelta(hours=3)
    assert report_a.metadata["contamination_free"] is True
    assert report_a.metadata["stable_benchmark"] is True
    assert report_a.content_hash == report_b.content_hash
    assert report_a.comparison_scope_hash == report_b.comparison_scope_hash


def test_forecast_uplift_comparison_report_tracks_enriched_vs_forecast_only() -> None:
    cutoff = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    records = [
        ForecastEvaluationRecord.evaluate(
            question_id="q1",
            market_id="pm_uplift_1",
            forecast_probability=0.74,
            resolved_outcome=True,
            cutoff_at=cutoff,
            model_family="forecast_only_model",
            market_family="macro",
            horizon_bucket="30d",
            market_baseline_probability=0.55,
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q2",
            market_id="pm_uplift_2",
            forecast_probability=0.26,
            resolved_outcome=False,
            cutoff_at=cutoff,
            model_family="forecast_only_model",
            market_family="macro",
            horizon_bucket="30d",
            market_baseline_probability=0.45,
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q1",
            market_id="pm_uplift_1",
            forecast_probability=0.88,
            resolved_outcome=True,
            cutoff_at=cutoff,
            model_family="enriched_model",
            market_family="macro",
            horizon_bucket="30d",
            market_baseline_probability=0.55,
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q2",
            market_id="pm_uplift_2",
            forecast_probability=0.12,
            resolved_outcome=False,
            cutoff_at=cutoff,
            model_family="enriched_model",
            market_family="macro",
            horizon_bucket="30d",
            market_baseline_probability=0.45,
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q3",
            market_id="pm_uplift_3",
            forecast_probability=0.61,
            resolved_outcome=True,
            cutoff_at=cutoff + timedelta(hours=1),
            model_family="enriched_model",
            market_family="macro",
            horizon_bucket="30d",
            market_baseline_probability=0.53,
        ),
    ]

    report = build_forecast_uplift_comparison_report(
        records,
        forecast_only_model_family="forecast_only_model",
        enriched_model_family="enriched_model",
        market_family="macro",
        horizon_bucket="30d",
        as_of=cutoff,
        metadata={"source": "unit-test"},
    )

    assert isinstance(report, ForecastUpliftComparisonReport)
    assert report.forecast_only_record_count == 2
    assert report.enriched_record_count == 2
    assert report.aligned_pair_count == 2
    assert report.brier_improvement > 0.0
    assert report.log_loss_improvement > 0.0
    assert report.market_baseline_delta_gap == pytest.approx(
        report.enriched_mean_market_baseline_delta - report.forecast_only_mean_market_baseline_delta
    )
    assert report.metadata["contamination_free"] is True
    assert report.metadata["stable_benchmark"] is True
    assert report.metadata["as_of_cutoff_at"] == cutoff.isoformat()
    assert report.metadata["aligned_pair_count"] == 2
    assert report.content_hash


def test_as_of_model_version_comparison_excludes_future_records() -> None:
    cutoff = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    records = [
        ForecastEvaluationRecord.evaluate(
            question_id="q1",
            market_id="pm_eval_1",
            forecast_probability=0.82,
            resolved_outcome=True,
            cutoff_at=cutoff - timedelta(hours=1),
            model_family="model_v1",
            market_family="macro",
            horizon_bucket="30d",
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q1",
            market_id="pm_eval_1",
            forecast_probability=0.61,
            resolved_outcome=True,
            cutoff_at=cutoff - timedelta(hours=1),
            model_family="model_v2",
            market_family="macro",
            horizon_bucket="30d",
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q2",
            market_id="pm_eval_2",
            forecast_probability=0.14,
            resolved_outcome=False,
            cutoff_at=cutoff + timedelta(hours=1),
            model_family="model_v1",
            market_family="macro",
            horizon_bucket="30d",
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q2",
            market_id="pm_eval_2",
            forecast_probability=0.33,
            resolved_outcome=False,
            cutoff_at=cutoff + timedelta(hours=1),
            model_family="model_v2",
            market_family="macro",
            horizon_bucket="30d",
        ),
    ]

    report = build_model_version_comparison_report(
        records,
        left_model_family="model_v1",
        right_model_family="model_v2",
        market_family="macro",
        horizon_bucket="30d",
        as_of=cutoff,
    )

    assert report.aligned_pair_count == 1
    assert report.unpaired_left_count == 0
    assert report.unpaired_right_count == 0
    assert report.comparison_pairs[0].question_id == "q1"
    assert report.metadata["contamination_free"] is True
    assert report.metadata["as_of_cutoff_at"] == cutoff.isoformat()


def test_as_of_calibration_snapshot_filters_future_records() -> None:
    cutoff = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    records = [
        ForecastEvaluationRecord.evaluate(
            question_id="q1",
            market_id="pm_eval_1",
            forecast_probability=0.9,
            resolved_outcome=True,
            cutoff_at=cutoff - timedelta(hours=2),
            market_family="macro",
            horizon_bucket="30d",
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q2",
            market_id="pm_eval_1",
            forecast_probability=0.1,
            resolved_outcome=False,
            cutoff_at=cutoff + timedelta(hours=2),
            market_family="macro",
            horizon_bucket="30d",
        ),
    ]

    snapshot = build_as_of_calibration_snapshot(
        records,
        as_of=cutoff,
        model_family="demo-model",
        market_family="macro",
        horizon_bucket="30d",
        metadata={"source": "unit-test"},
    )

    assert snapshot.record_count == 1
    assert snapshot.evaluation_refs == [records[0].evaluation_id]
    assert snapshot.metadata["as_of_cutoff_at"] == cutoff.isoformat()
    assert snapshot.metadata["contamination_free"] is True
    assert snapshot.metadata["excluded_future_record_count"] == 1
    assert snapshot.coverage == pytest.approx(1.0)
    assert snapshot.content_hash


def test_as_of_benchmark_suite_compares_market_only_single_llm_ensemble_and_decision_packet_assisted(tmp_path) -> None:
    cutoff = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    findings = [
        _evidence("e1", claim="Bullish catalyst", observed_at=cutoff - timedelta(hours=3), stance="bullish"),
        _evidence("e2", claim="Bearish risk", observed_at=cutoff - timedelta(hours=1), stance="bearish"),
        _evidence("e3", claim="Future signal", observed_at=cutoff + timedelta(hours=1), stance="neutral"),
    ]
    records = [
        ForecastEvaluationRecord.evaluate(
            question_id="q1",
            market_id="pm_eval_suite",
            forecast_probability=0.53,
            resolved_outcome=True,
            cutoff_at=cutoff - timedelta(hours=2),
            model_family="market_only_model",
            market_family="macro",
            horizon_bucket="30d",
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q1",
            market_id="pm_eval_suite",
            forecast_probability=0.68,
            resolved_outcome=True,
            cutoff_at=cutoff - timedelta(hours=2),
            model_family="single_llm_model",
            market_family="macro",
            horizon_bucket="30d",
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q1",
            market_id="pm_eval_suite",
            forecast_probability=0.74,
            resolved_outcome=True,
            cutoff_at=cutoff - timedelta(hours=2),
            model_family="ensemble_model",
            market_family="macro",
            horizon_bucket="30d",
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q1",
            market_id="pm_eval_suite",
            forecast_probability=0.71,
            resolved_outcome=True,
            cutoff_at=cutoff - timedelta(hours=2),
            model_family="decision_packet_assisted_model",
            market_family="macro",
            horizon_bucket="30d",
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q2",
            market_id="pm_eval_suite",
            forecast_probability=0.21,
            resolved_outcome=False,
            cutoff_at=cutoff + timedelta(hours=1),
            model_family="ensemble_model",
            market_family="macro",
            horizon_bucket="30d",
        ),
    ]

    suite = build_as_of_benchmark_suite(
        findings,
        records,
        market_id="pm_eval_suite",
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
        external_baselines={"external_reference": 0.62},
        metadata={"source": "unit-test"},
    )

    assert isinstance(suite, AsOfBenchmarkSuite)
    assert suite.contamination_free is True
    assert suite.stable_benchmark is True
    assert suite.excluded_future_evaluation_count == 1
    assert suite.excluded_future_finding_count == 1
    assert suite.evidence_set.metadata["contamination_free"] is True
    assert suite.research_report.as_of_cutoff_at == cutoff
    assert len(suite.family_summaries) == 4
    assert {summary.family_role for summary in suite.family_summaries} == {
        "market-only",
        "single-LLM",
        "ensemble",
        "DecisionPacket-assisted",
    }
    assert all(summary.contamination_free is True for summary in suite.family_summaries)
    assert all("brier_score" in summary.canonical_score_components for summary in suite.family_summaries)
    assert suite.canonical_score_components["brier_score"] >= 0.0
    assert suite.canonical_score_components["log_loss"] >= 0.0
    assert suite.canonical_score_components["ece"] >= 0.0
    assert 0.0 <= suite.canonical_score_components["abstention_coverage"] <= 1.0
    assert suite.calibration_snapshot is not None
    assert suite.calibration_snapshot.record_count == 1
    assert any(report.metadata.get("left_family_label") == "market-only" for report in suite.model_version_comparisons)
    assert any(report.metadata.get("right_family_label") == "ensemble" for report in suite.model_version_comparisons)
    assert len(suite.model_version_comparisons) == 6
    assert len(suite.baseline_comparisons) >= 4
    persisted = suite.persist(tmp_path / "benchmark_suite.json")
    loaded = AsOfBenchmarkSuite.load(persisted)
    assert loaded.content_hash == suite.content_hash
    assert loaded.canonical_score_components == suite.canonical_score_components
    assert loaded.family_summaries[0].content_hash == suite.family_summaries[0].content_hash


def test_research_report_and_harness_persist_roundtrip(tmp_path) -> None:
    harness = ForecastEvaluationHarness(base_dir=tmp_path)
    forecast = _forecast()
    cutoff = datetime(2026, 4, 8, 0, 0, tzinfo=timezone.utc)
    evidence = [
        _evidence("e1", claim="Bullish catalyst", observed_at=cutoff - timedelta(hours=4), stance="bullish"),
        _evidence("e2", claim="Bearish risk", observed_at=cutoff - timedelta(hours=1), stance="bearish"),
    ]

    record = harness.evaluate_forecast(
        forecast,
        question_id="q_eval_2",
        resolved_outcome=True,
        market_baseline_probability=0.5,
        market_family="macro",
        horizon_bucket="30d",
        evidence_packets=evidence,
        cutoff_at=cutoff,
    )
    evidence_set = harness.build_as_of_evidence_set(
        evidence,
        market_id="pm_eval_1",
        cutoff_at=cutoff,
        retrieval_policy="as_of",
        metadata={"source": "unit-test"},
    )
    report = harness.build_research_report(
        evidence_set,
        evidence,
        facts=["Bullish catalyst"],
        theses=["Bullish catalyst"],
        objections=["Bearish risk"],
        key_factors=["Bullish catalyst"],
        counterarguments=["Bearish risk"],
        open_questions=["Will follow-up evidence confirm the move?"],
    )
    snapshot = harness.summarize_calibration(
        [record],
        model_family="demo-model",
        market_family="macro",
        horizon_bucket="30d",
    )
    priors = harness.fit_base_rates([record])

    assert record.forecast_ref == forecast.forecast_id
    assert record.evidence_refs == ["evid_a", "evid_b", "e1", "e2"]
    assert evidence_set.evidence_refs == ["e1", "e2"]
    assert report.base_rates["bullish_share"] == pytest.approx(0.5)
    assert report.facts == ["Bullish catalyst"]
    assert report.theses == ["Bullish catalyst"]
    assert report.objections == ["Bearish risk"]
    assert report.supporting_evidence_refs == ["e1", "e2"]
    assert report.counterarguments == ["Bearish risk"]
    assert report.summary == "Research report for pm_eval_1"
    assert report.evidence_set_id == evidence_set.evidence_set_id
    assert report.as_of_cutoff_at == evidence_set.cutoff_at
    assert report.content_hash
    assert snapshot.record_count == 1
    assert snapshot.content_hash
    assert priors["macro"] == pytest.approx(1.0)

    persisted_record = next((harness.store.root / "records").glob("*.json"))
    reloaded = ForecastEvaluationRecord.model_validate_json(persisted_record.read_text(encoding="utf-8"))
    assert reloaded.evaluation_id == record.evaluation_id
    assert reloaded.market_id == "pm_eval_1"

    report_files = list((harness.store.root / "reports").glob("*.json"))
    assert report_files
    loaded_report = ResearchReport.model_validate_json(report_files[0].read_text(encoding="utf-8"))
    assert loaded_report.market_id == "pm_eval_1"
    assert loaded_report.summary == report.summary
    assert loaded_report.evidence_set_id == report.evidence_set_id
    assert loaded_report.as_of_cutoff_at == report.as_of_cutoff_at
    assert loaded_report.content_hash == report.content_hash
