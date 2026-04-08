from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from prediction_markets import MarketAdvisor, PredictionMarketPaths
from prediction_markets.calibration_lab import (
    CalibrationLab,
    CalibrationHistoryStore,
    CalibrationLabel,
    CalibrationScore,
)
from prediction_markets.forecast_evaluation import ForecastEvaluationRecord
from prediction_markets.models import DecisionAction, ForecastPacket, VenueName


def test_calibration_history_store_roundtrip(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    store = CalibrationHistoryStore(paths)

    label = CalibrationLabel(
        run_id="run_1",
        market_id="pm_demo_election",
        outcome_yes=True,
        created_at="2026-04-07T00:00:00Z",
    )
    store.record_label(label)

    loaded = store.get_label("run_1")
    assert loaded is not None
    assert loaded.outcome_yes is True
    assert store.labels_path.exists()


def test_calibration_lab_scores_persisted_run_and_replay(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    advisor = MarketAdvisor(paths=paths, backend_mode="surrogate")
    run = advisor.advise("polymarket-fed-cut-q3-2026", persist=True, run_id="run_1")

    lab = CalibrationLab(base_dir=paths.root, replay_backend_mode="surrogate")
    lab.record_label(
        run.run_id,
        market_id=run.market.market_id,
        outcome_yes=True,
        source="manual",
        note="Synthetic label for calibration testing.",
    )

    score = lab.score_run(run.run_id)

    assert score.run_id == run.run_id
    assert score.market_id == run.market.market_id
    assert 0.0 <= score.brier_score <= 1.0
    assert score.log_loss >= 0.0
    assert score.hit == (((score.probability_yes >= 0.5) == score.outcome_yes))
    assert score.score_components["brier_score"] == pytest.approx(round(score.brier_score, 6))
    assert score.score_components["log_loss"] == pytest.approx(round(score.log_loss, 6))
    assert score.score_components["hit"] in {0.0, 1.0}
    assert score.postmortem().closing_line_drift_bps == pytest.approx(score.closing_line_drift_bps)
    assert score.replay_consistent is True
    assert score.replay_report is not None

    summary = lab.summarize()
    report = lab.report()
    assert summary.count == 1
    assert summary.mean_brier_score == pytest.approx(score.brier_score)
    assert summary.mean_log_loss == pytest.approx(score.log_loss)
    assert summary.mean_ece == pytest.approx(abs(score.probability_yes - float(score.outcome_yes)))
    assert summary.mean_sharpness == pytest.approx(abs(score.probability_yes - 0.5) * 2.0)
    assert 0.0 <= summary.abstention_coverage <= 1.0
    assert summary.mean_market_baseline_delta_bps == pytest.approx(summary.mean_market_baseline_delta * 10000.0)
    assert summary.content_hash
    assert summary.hit_rate == pytest.approx(1.0 if score.hit else 0.0)
    assert summary.mean_closing_line_drift_bps == pytest.approx(score.closing_line_drift_bps)
    assert summary.mean_edge_after_fees_bps == pytest.approx(score.edge_after_fees_bps)
    assert summary.replay_consistency_rate == pytest.approx(1.0)
    assert report.summary.count == 1
    assert report.summary.hit_rate == pytest.approx(summary.hit_rate)
    assert len(report.scores) == 1
    assert report.scores[0].score_components == score.score_components
    assert len(report.postmortems) == 1
    assert report.postmortems[0].closing_line_drift_bps == pytest.approx(score.closing_line_drift_bps)
    assert report.postmortems[0].edge_after_fees_bps == pytest.approx(score.edge_after_fees_bps)
    assert report.content_hash
    assert report.metadata["mean_market_baseline_delta_bps"] == pytest.approx(summary.mean_market_baseline_delta_bps)

    persisted_report = report.persist(tmp_path / "calibration_report.json")
    loaded_report = type(report).load(persisted_report)
    assert loaded_report.report_id == report.report_id
    assert loaded_report.summary.count == report.summary.count
    assert loaded_report.summary.hit_rate == pytest.approx(report.summary.hit_rate)
    assert loaded_report.content_hash == report.content_hash
    assert loaded_report.summary.content_hash == report.summary.content_hash


def test_calibration_lab_aggregates_multiple_runs(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    advisor = MarketAdvisor(paths=paths, backend_mode="surrogate")
    lab = CalibrationLab(base_dir=paths.root, replay_backend_mode="surrogate")

    run_yes = advisor.advise("polymarket-fed-cut-q3-2026", persist=True, run_id="run_yes")
    run_no = advisor.advise("polymarket-btc-above-120k-2026", persist=True, run_id="run_no")

    lab.record_label(run_yes.run_id, market_id=run_yes.market.market_id, outcome_yes=True)
    lab.record_label(run_no.run_id, market_id=run_no.market.market_id, outcome_yes=False)

    scores = lab.score_runs([run_yes.run_id, run_no.run_id])
    summary = lab.summarize(scores)
    report = lab.report(scores)

    assert summary.count == 2
    assert summary.labels == {"yes": 1, "no": 1}
    assert summary.mean_probability_yes == pytest.approx(
        sum(score.probability_yes for score in scores) / 2.0
    )
    assert summary.mean_outcome_yes == pytest.approx(0.5)
    assert summary.hit_rate == pytest.approx(sum(1.0 if score.hit else 0.0 for score in scores) / 2.0)
    assert summary.mean_closing_line_drift_bps == pytest.approx(
        sum(score.closing_line_drift_bps for score in scores) / 2.0
    )
    assert summary.mean_brier_score >= 0.0
    assert summary.mean_log_loss >= 0.0
    assert summary.mean_ece >= 0.0
    assert summary.mean_sharpness >= 0.0
    assert report.summary.count == 2
    assert report.summary.hit_rate == pytest.approx(summary.hit_rate)
    assert len(report.postmortems) == 2
    assert {item.run_id for item in report.postmortems} == {run_yes.run_id, run_no.run_id}


def test_calibration_lab_summarize_calibration_as_of_is_contamination_free(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    lab = CalibrationLab(base_dir=paths.root, replay_backend_mode="surrogate")
    as_of = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    records = [
        ForecastEvaluationRecord.evaluate(
            question_id="q_before",
            market_id="pm_eval_before",
            forecast_probability=0.74,
            resolved_outcome=True,
            cutoff_at=as_of - timedelta(hours=2),
            model_family="demo-model",
            market_family="macro",
            horizon_bucket="30d",
        ),
        ForecastEvaluationRecord.evaluate(
            question_id="q_after",
            market_id="pm_eval_after",
            forecast_probability=0.26,
            resolved_outcome=False,
            cutoff_at=as_of + timedelta(hours=2),
            model_family="demo-model",
            market_family="macro",
            horizon_bucket="30d",
        ),
    ]

    snapshot = lab.summarize_calibration_as_of(
        records,
        as_of=as_of,
        model_family="demo-model",
        market_family="macro",
        horizon_bucket="30d",
        metadata={"source": "unit-test"},
    )

    assert snapshot.record_count == 1
    assert snapshot.evaluation_refs == [records[0].evaluation_id]
    assert snapshot.metadata["as_of_cutoff_at"] == as_of.isoformat()
    assert snapshot.metadata["contamination_free"] is True
    assert snapshot.metadata["included_record_count"] == 1
    assert snapshot.metadata["excluded_future_record_count"] == 1
    assert snapshot.coverage == pytest.approx(1.0)
    assert snapshot.mean_brier_score == pytest.approx(records[0].brier_score)
    assert snapshot.mean_log_loss == pytest.approx(records[0].log_loss)
    assert (lab.store.root / "snapshots").exists()


def test_calibration_lab_curve_segment_and_closing_line_reports(tmp_path: Path) -> None:
    lab = CalibrationLab(base_dir=tmp_path / "prediction_markets", replay_backend_mode="surrogate")

    def _score(
        *,
        run_id: str,
        market_id: str,
        probability_yes: float,
        outcome_yes: bool,
        category: str,
        horizon_bucket: str,
        abstain: bool = False,
        market_implied_probability: float = 0.5,
        edge_after_fees_bps: float = 0.0,
    ) -> CalibrationScore:
        forecast = ForecastPacket(
            run_id=run_id,
            market_id=market_id,
            venue=VenueName.polymarket,
            market_implied_probability=market_implied_probability,
            fair_probability=probability_yes,
            confidence_low=max(0.0, probability_yes - 0.08),
            confidence_high=min(1.0, probability_yes + 0.08),
            edge_bps=(probability_yes - market_implied_probability) * 10000.0,
            edge_after_fees_bps=edge_after_fees_bps,
            recommendation_action=DecisionAction.manual_review if abstain else DecisionAction.bet,
            manual_review_required=abstain,
            model_used="demo-model",
            metadata={
                "category": category,
                "horizon_bucket": horizon_bucket,
                "market_family": "macro",
            },
        )
        return CalibrationScore(
            run_id=run_id,
            market_id=market_id,
            venue=VenueName.polymarket,
            probability_yes=probability_yes,
            outcome_yes=outcome_yes,
            hit=((probability_yes >= 0.5) == outcome_yes),
            brier_score=(probability_yes - float(outcome_yes)) ** 2,
            log_loss=-math.log(probability_yes if outcome_yes else 1.0 - probability_yes),
            closing_line_drift_bps=(probability_yes - market_implied_probability) * 10000.0,
            edge_after_fees_bps=edge_after_fees_bps,
            forecast=forecast,
            metadata={
                "category": category,
                "horizon_bucket": horizon_bucket,
                "market_family": "macro",
                "model_family": "demo-model",
            },
        )

    scores = [
        _score(
            run_id="run_active_1",
            market_id="pm_macro_1",
            probability_yes=0.91,
            outcome_yes=True,
            category="macro-growth",
            horizon_bucket="30d",
            edge_after_fees_bps=42.0,
        ),
        _score(
            run_id="run_active_2",
            market_id="pm_macro_2",
            probability_yes=0.16,
            outcome_yes=False,
            category="macro-growth",
            horizon_bucket="30d",
            edge_after_fees_bps=18.0,
        ),
        _score(
            run_id="run_abstain_1",
            market_id="pm_macro_3",
            probability_yes=0.53,
            outcome_yes=True,
            category="macro-growth",
            horizon_bucket="30d",
            abstain=True,
            edge_after_fees_bps=-8.0,
        ),
        _score(
            run_id="run_abstain_2",
            market_id="pm_micro_1",
            probability_yes=0.47,
            outcome_yes=False,
            category="micro-liquidity",
            horizon_bucket="90d",
            abstain=True,
            edge_after_fees_bps=-12.0,
        ),
    ]

    curve = lab.calibration_curve(scores)
    performance = lab.performance_by_category_and_horizon(scores)
    abstention = lab.abstention_quality(scores)
    closing_line = lab.closing_line_quality(scores)
    closing_line_reversed = lab.closing_line_quality(list(reversed(scores)))

    assert curve.record_count == 4
    assert curve.active_count == 2
    assert curve.abstain_count == 2
    assert curve.bucket_summaries
    assert curve.content_hash
    assert performance.segment_count == 2
    assert any(segment.category == "macro-growth" for segment in performance.segments)
    assert any(segment.horizon_bucket == "90d" for segment in performance.segments)
    assert performance.content_hash
    assert abstention.record_count == 4
    assert abstention.abstain_count == 2
    assert abstention.mean_abstention_brier_gap > 0.0
    assert abstention.mean_abstention_margin_gap > 0.0
    assert abstention.content_hash
    assert closing_line.record_count == 4
    assert closing_line.segment_count == 2
    assert closing_line.mean_closing_line_drift_bps == pytest.approx(
        sum(score.closing_line_drift_bps for score in scores) / 4.0
    )
    assert closing_line.mean_abs_closing_line_drift_bps >= 0.0
    assert closing_line.mean_abs_edge_after_fees_bps >= 0.0
    assert closing_line.segments[0].content_hash
    assert closing_line.content_hash == closing_line_reversed.content_hash
    assert closing_line_reversed.segment_count == closing_line.segment_count
