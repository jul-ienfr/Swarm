from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from pathlib import Path

from swarm_core.deliberation_campaign import (
    DeliberationCampaignBenchmarkBundle,
    DeliberationCampaignComparisonAudit,
    DeliberationCampaignComparisonBundle,
    DeliberationCampaignComparisonExport,
    DeliberationCampaignArtifactIndex,
    DeliberationCampaignDashboard,
    DeliberationCampaignMatrixBenchmarkComparisonAudit,
    DeliberationCampaignMatrixBenchmarkComparisonBundle,
    DeliberationCampaignMatrixBenchmarkComparisonExport,
    DeliberationCampaignMatrixBenchmarkComparisonReport,
    DeliberationCampaignMatrixBenchmarkExportComparisonAudit,
    DeliberationCampaignMatrixBenchmarkExportComparisonBundle,
    DeliberationCampaignMatrixBenchmarkExportComparisonExport,
    DeliberationCampaignMatrixBenchmarkExportComparisonReport,
    DeliberationCampaignStatus,
    DeliberationCampaignReport,
    DeliberationCampaignMatrixBenchmarkBundle,
    DeliberationCampaignMatrixBenchmarkAudit,
    DeliberationCampaignMatrixBenchmarkExport,
    DeliberationCampaignMatrixBenchmarkSummary,
    DeliberationCampaignMatrixCandidateSpec,
    build_deliberation_campaign_artifact_index,
    build_deliberation_campaign_dashboard,
    build_deliberation_campaign_comparison_audit,
    build_deliberation_campaign_matrix_benchmark_audit,
    build_deliberation_campaign_matrix_benchmark_export,
    build_deliberation_campaign_matrix_benchmark_export_comparison_audit,
    build_deliberation_campaign_matrix_benchmark_export_comparison_export,
    build_deliberation_campaign_matrix_benchmark_comparison_audit,
    build_deliberation_campaign_matrix_benchmark_comparison_export,
    compare_deliberation_campaign_bundle,
    compare_deliberation_campaign_matrix_benchmark_export_comparison_bundle,
    compare_deliberation_campaign_matrix_benchmark_exports,
    compare_deliberation_campaign_matrix_benchmarks,
    compare_deliberation_campaign_matrix_benchmark_comparison_bundle,
    build_deliberation_campaign_comparison_export,
    compare_deliberation_campaign_reports,
    load_deliberation_campaign_comparison_export,
    load_deliberation_campaign_comparison_report,
    load_deliberation_campaign_comparison_audit,
    load_deliberation_campaign_benchmark,
    load_deliberation_campaign_matrix_benchmark_audit,
    load_deliberation_campaign_matrix_benchmark_export_comparison_report,
    load_deliberation_campaign_matrix_benchmark_export_comparison_audit,
    load_deliberation_campaign_matrix_benchmark_export_comparison_export,
    load_deliberation_campaign_matrix_benchmark_comparison_report,
    load_deliberation_campaign_matrix_benchmark_comparison_audit,
    load_deliberation_campaign_matrix_benchmark_comparison_export,
    load_deliberation_campaign_matrix_benchmark_export,
    load_deliberation_campaign_matrix_benchmark,
    load_deliberation_campaign_report,
    list_deliberation_campaign_benchmarks,
    list_deliberation_campaign_matrix_benchmark_audits,
    list_deliberation_campaign_matrix_benchmark_export_comparison_reports,
    list_deliberation_campaign_matrix_benchmark_export_comparison_exports,
    list_deliberation_campaign_matrix_benchmark_comparison_reports,
    list_deliberation_campaign_matrix_benchmark_comparison_exports,
    list_deliberation_campaign_matrix_benchmark_exports,
    list_deliberation_campaign_matrix_benchmarks,
    list_deliberation_campaign_comparison_exports,
    list_deliberation_campaign_comparison_reports,
    list_deliberation_campaign_reports,
    materialize_deliberation_campaign_comparison_export,
    materialize_deliberation_campaign_matrix_benchmark_export,
    materialize_deliberation_campaign_matrix_benchmark_export_comparison_export,
    materialize_deliberation_campaign_matrix_benchmark_comparison_export,
    render_deliberation_campaign_comparison_markdown,
    run_deliberation_campaign_benchmark_sync,
    run_deliberation_campaign_matrix_benchmark_sync,
    run_deliberation_campaign_sync,
)
from swarm_core.deliberation_artifacts import DeliberationMode
from swarm_core.deliberation_stability import DeliberationStabilitySummary


class FakeResult:
    def __init__(
        self,
        *,
        deliberation_id: str,
        score: float,
        confidence: float,
        runtime_used: str,
        fallback_used: bool,
        engine_used: str = "agentsociety",
    ) -> None:
        self.deliberation_id = deliberation_id
        self.topic = "Choose the launch strategy"
        self.objective = "Define the best strategy"
        self.status = SimpleNamespace(value="completed")
        self.runtime_requested = "pydanticai"
        self.runtime_used = runtime_used
        self.fallback_used = fallback_used
        self.engine_requested = "agentsociety"
        self.engine_used = engine_used
        self.summary = f"summary-{deliberation_id}"
        self.final_strategy = f"strategy-{deliberation_id}"
        self.judge_scores = SimpleNamespace(overall=score)
        self.confidence_level = confidence
        self.stability_summary = DeliberationStabilitySummary.from_scores(
            [score, min(1.0, score + 0.02)],
            metric_name="sample_quality",
            comparison_key=deliberation_id,
            sample_run_ids=[f"{deliberation_id}_a", f"{deliberation_id}_b"],
        )
        self.metadata = {
            "comparability": {
                "runtime_used": runtime_used,
                "engine_used": engine_used,
                "fallback_used": fallback_used,
            },
            "quality_warnings": ["runtime_fallback_used"] if fallback_used else [],
            "runtime_resilience": {
                "status": "guarded" if not fallback_used else "degraded",
                "attempt_count": 1 if not fallback_used else 2,
            },
        }

    def model_dump(self, mode: str = "json") -> dict[str, object]:
        return {
            "deliberation_id": self.deliberation_id,
            "topic": self.topic,
            "objective": self.objective,
            "status": self.status.value,
            "runtime_requested": self.runtime_requested,
            "runtime_used": self.runtime_used,
            "fallback_used": self.fallback_used,
            "engine_requested": self.engine_requested,
            "engine_used": self.engine_used,
            "summary": self.summary,
            "final_strategy": self.final_strategy,
            "confidence_level": self.confidence_level,
            "judge_scores": {"overall": self.judge_scores.overall},
            "metadata": self.metadata,
        }


def _write_campaign_report(base_dir: Path, report: DeliberationCampaignReport) -> None:
    campaign_dir = base_dir / report.campaign_id
    campaign_dir.mkdir(parents=True, exist_ok=True)
    (campaign_dir / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")


def _write_matrix_benchmark_report(base_dir: Path, benchmark: DeliberationCampaignMatrixBenchmarkBundle) -> None:
    benchmark_dir = base_dir / benchmark.benchmark_id
    benchmark_dir.mkdir(parents=True, exist_ok=True)
    report_path = benchmark_dir / "report.json"
    persisted = benchmark.model_copy(update={"report_path": str(report_path)})
    report_path.write_text(persisted.model_dump_json(indent=2), encoding="utf-8")


def _campaign_report_with_updates(
    base_report: DeliberationCampaignReport,
    *,
    campaign_id: str,
    created_at: datetime,
    topic: str | None = None,
    mode: DeliberationMode | None = None,
    runtime_requested: str | None = None,
    engine_requested: str | None = None,
    sample_count_requested: int | None = None,
    stability_runs: int | None = None,
    comparison_key: str | None = None,
) -> DeliberationCampaignReport:
    summary = base_report.summary
    if comparison_key is not None and summary.campaign_stability_summary is not None:
        stability_summary = summary.campaign_stability_summary.model_copy(update={"comparison_key": comparison_key})
        summary = summary.model_copy(update={"campaign_stability_summary": stability_summary})

    updates: dict[str, object] = {
        "campaign_id": campaign_id,
        "created_at": created_at,
        "summary": summary,
    }
    if topic is not None:
        updates["topic"] = topic
    if mode is not None:
        updates["mode"] = mode
    if runtime_requested is not None:
        updates["runtime_requested"] = runtime_requested
    if engine_requested is not None:
        updates["engine_requested"] = engine_requested
    if sample_count_requested is not None:
        updates["sample_count_requested"] = sample_count_requested
    if stability_runs is not None:
        updates["stability_runs"] = stability_runs
    return base_report.model_copy(update=updates)


def _matrix_benchmark_bundle_with_updates(
    base_report: DeliberationCampaignReport,
    *,
    benchmark_id: str,
    created_at: datetime,
    topic: str | None = None,
    mode: DeliberationMode | None = None,
    baseline_runtime: str | None = None,
    baseline_engine: str | None = None,
    sample_count_requested: int | None = None,
    stability_runs: int | None = None,
    candidate_specs: list[DeliberationCampaignMatrixCandidateSpec] | None = None,
    quality_score_mean: float = 0.8,
    confidence_level_mean: float = 0.76,
    mismatch_count: int = 0,
    comparable_count: int | None = None,
    report_path: str | None = None,
) -> DeliberationCampaignMatrixBenchmarkBundle:
    normalized_candidate_specs = candidate_specs or [
        DeliberationCampaignMatrixCandidateSpec(
            label="Legacy candidate",
            campaign_id=f"{benchmark_id}__candidate_legacy",
            runtime="legacy",
            engine_preference="oasis",
        ),
        DeliberationCampaignMatrixCandidateSpec(
            label="Hybrid candidate",
            campaign_id=f"{benchmark_id}__candidate_hybrid",
            runtime="hybrid",
            engine_preference="agentsociety",
        ),
    ]
    baseline_campaign = base_report.model_copy(
        update={
            "campaign_id": f"{benchmark_id}__baseline",
            "created_at": created_at,
            "topic": topic if topic is not None else base_report.topic,
            "mode": mode if mode is not None else base_report.mode,
            "runtime_requested": baseline_runtime if baseline_runtime is not None else base_report.runtime_requested,
            "engine_requested": baseline_engine if baseline_engine is not None else base_report.engine_requested,
            "sample_count_requested": sample_count_requested if sample_count_requested is not None else base_report.sample_count_requested,
            "stability_runs": stability_runs if stability_runs is not None else base_report.stability_runs,
        }
    )
    candidate_labels = [
        spec.label or f"candidate_{index:02d}"
        for index, spec in enumerate(normalized_candidate_specs, start=1)
    ]
    candidate_campaign_ids = [
        spec.campaign_id or f"{benchmark_id}__candidate_{index:02d}"
        for index, spec in enumerate(normalized_candidate_specs, start=1)
    ]
    comparison_ids = [
        f"{baseline_campaign.campaign_id}__vs__{candidate_campaign_id}"
        for candidate_campaign_id in candidate_campaign_ids
    ]
    runtime_values = list(
        dict.fromkeys(
            [
                baseline_campaign.runtime_requested,
                *[str(spec.runtime) for spec in normalized_candidate_specs],
            ]
        )
    )
    engine_values = list(
        dict.fromkeys(
            [
                baseline_campaign.engine_requested,
                *[
                    getattr(spec.engine_preference, "value", spec.engine_preference)
                    for spec in normalized_candidate_specs
                ],
            ]
        )
    )
    candidate_count = len(normalized_candidate_specs)
    effective_comparable_count = comparable_count if comparable_count is not None else max(0, candidate_count - mismatch_count)
    summary = DeliberationCampaignMatrixBenchmarkSummary(
        candidate_count=candidate_count,
        candidate_labels=candidate_labels,
        candidate_campaign_ids=candidate_campaign_ids,
        comparison_ids=comparison_ids,
        comparable_count=effective_comparable_count,
        mismatch_count=mismatch_count,
        status_counts={
            "comparable": effective_comparable_count,
            "mismatch": mismatch_count,
        },
        runtime_values=runtime_values,
        engine_values=engine_values,
        quality_score_mean=quality_score_mean,
        quality_score_min=max(0.0, quality_score_mean - 0.03),
        quality_score_max=min(1.0, quality_score_mean + 0.03),
        confidence_level_mean=confidence_level_mean,
        confidence_level_min=max(0.0, confidence_level_mean - 0.03),
        confidence_level_max=min(1.0, confidence_level_mean + 0.03),
        metadata={"benchmark_id": benchmark_id},
    )
    return DeliberationCampaignMatrixBenchmarkBundle(
        benchmark_id=benchmark_id,
        created_at=created_at,
        output_dir="/tmp/matrix_benchmarks",
        report_path=report_path,
        baseline_campaign=baseline_campaign,
        candidate_specs=normalized_candidate_specs,
        entries=[],
        summary=summary,
        metadata={
            "benchmark_id": benchmark_id,
            "baseline_campaign_id": baseline_campaign.campaign_id,
            "candidate_count": candidate_count,
            "candidate_campaign_ids": candidate_campaign_ids,
            "candidate_labels": candidate_labels,
            "comparison_ids": comparison_ids,
        },
    )


def test_campaign_disables_fallback_for_repeated_samples_and_aggregates_counts() -> None:
    calls: list[dict[str, object]] = []

    def fake_runner(**kwargs):
        calls.append(kwargs)
        index = len(calls)
        return FakeResult(
            deliberation_id=f"delib_{index}",
            score=0.6 + (index * 0.1),
            confidence=0.5 + (index * 0.05),
            runtime_used="legacy" if index == 1 else "pydanticai",
            fallback_used=False,
            engine_used="agentsociety" if index != 3 else "oasis",
        )

    report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=3,
        stability_runs=2,
        allow_fallback=True,
        runner=fake_runner,
        persist=False,
    )

    assert len(calls) == 3
    assert all(call["allow_fallback"] is False for call in calls)
    assert all(call["stability_runs"] == 2 for call in calls)
    assert report.status == DeliberationCampaignStatus.completed
    assert report.fallback_guard_applied is True
    assert report.fallback_guard_reason == "fallback_disabled_for_repeated_campaign_comparison"
    assert report.allow_fallback_effective is False
    assert report.summary.sample_count_requested == 3
    assert report.summary.sample_count_completed == 3
    assert report.summary.sample_count_failed == 0
    assert report.summary.sample_ids == ["sample_01", "sample_02", "sample_03"]
    assert report.summary.deliberation_ids == ["delib_1", "delib_2", "delib_3"]
    assert report.summary.runtime_counts == {"legacy": 1, "pydanticai": 2}
    assert report.summary.engine_counts == {"agentsociety": 2, "oasis": 1}
    assert report.summary.status_counts == {"completed": 3}
    assert report.summary.quality_score_mean > 0.0
    assert report.summary.confidence_level_mean > 0.0
    assert report.summary.campaign_stability_summary is not None
    assert report.summary.campaign_stability_summary.sample_count == 3
    assert report.summary.campaign_stability_summary.sample_run_ids == ["delib_1", "delib_2", "delib_3"]
    assert report.metadata["campaign_fallback_guard_applied"] is True
    assert report.samples[0].comparability["campaign_fallback_guard_reason"] == "fallback_disabled_for_repeated_campaign_comparison"
    assert report.samples[0].quality_warnings == []


def test_campaign_persists_and_loads_round_trip(tmp_path) -> None:
    calls: list[dict[str, object]] = []

    def runner(**kwargs):
        calls.append(kwargs)
        return FakeResult(
            deliberation_id=f"delib_{len(calls)}",
            score=0.7,
            confidence=0.65,
            runtime_used="pydanticai",
            fallback_used=False,
        )

    report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=2,
        allow_fallback=False,
        runner=runner,
        persist=True,
        output_dir=tmp_path,
    )

    assert report.report_path is not None
    assert (tmp_path / report.campaign_id / "report.json").exists()
    assert (tmp_path / report.campaign_id / "samples" / "sample_01" / "result.json").exists()
    assert (tmp_path / report.campaign_id / "samples" / "sample_02" / "result.json").exists()

    loaded = load_deliberation_campaign_report(report.campaign_id, output_dir=tmp_path)

    assert loaded.campaign_id == report.campaign_id
    assert loaded.summary.sample_ids == ["sample_01", "sample_02"]
    assert loaded.summary.deliberation_ids == ["delib_1", "delib_2"]
    assert loaded.summary.sample_count_requested == 2
    assert loaded.allow_fallback_requested is False
    assert loaded.allow_fallback_effective is False
    assert loaded.status == DeliberationCampaignStatus.completed


def test_campaign_comparison_loads_explicit_reports_and_aggregates_homogeneous_metrics(tmp_path) -> None:
    base_report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        allow_fallback=False,
        runner=lambda **kwargs: FakeResult(
            deliberation_id="delib_compare",
            score=0.75,
            confidence=0.7,
            runtime_used="pydanticai",
            fallback_used=False,
        ),
        persist=False,
    )

    report_a = _campaign_report_with_updates(
        base_report,
        campaign_id="campaign_a",
        created_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
    )
    report_b = _campaign_report_with_updates(
        base_report,
        campaign_id="campaign_b",
        created_at=datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
    )

    _write_campaign_report(tmp_path, report_a)
    _write_campaign_report(tmp_path, report_b)

    comparison = compare_deliberation_campaign_reports(
        campaign_ids=["campaign_a", "campaign_b"],
        output_dir=tmp_path,
    )

    assert comparison.requested_campaign_ids == ["campaign_a", "campaign_b"]
    assert comparison.summary.campaign_count == 2
    assert comparison.summary.campaign_ids == ["campaign_a", "campaign_b"]
    assert [entry.campaign_id for entry in comparison.entries] == ["campaign_a", "campaign_b"]
    assert comparison.summary.comparable is True
    assert comparison.summary.mismatch_reasons == []
    assert comparison.summary.topic_values == ["Choose the launch strategy"]
    assert comparison.summary.mode_values == [DeliberationMode.committee.value]
    assert comparison.summary.runtime_values == ["pydanticai"]
    assert comparison.summary.engine_values == ["agentsociety"]
    assert comparison.summary.sample_count_values == [1]
    assert comparison.summary.stability_runs_values == [1]
    assert comparison.summary.comparison_key_values == [report_a.summary.campaign_stability_summary.comparison_key]
    assert comparison.summary.status_counts == {"completed": 2}
    assert comparison.summary.sample_count_requested_total == 2
    assert comparison.summary.sample_count_completed_total == 2
    assert comparison.summary.sample_count_failed_total == 0


def test_campaign_comparison_latest_flags_mismatches_and_uses_latest_n(tmp_path) -> None:
    base_report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        allow_fallback=False,
        runner=lambda **kwargs: FakeResult(
            deliberation_id="delib_latest",
            score=0.76,
            confidence=0.71,
            runtime_used="pydanticai",
            fallback_used=False,
        ),
        persist=False,
    )

    report_old = _campaign_report_with_updates(
        base_report,
        campaign_id="campaign_old",
        created_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
        topic="Topic A",
        mode=DeliberationMode.committee,
        runtime_requested="legacy",
        engine_requested="agentsociety",
        sample_count_requested=2,
        stability_runs=3,
        comparison_key="comparison-old",
    )
    report_mid = _campaign_report_with_updates(
        base_report,
        campaign_id="campaign_mid",
        created_at=datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
        topic="Topic B",
        mode=DeliberationMode.simulation,
        runtime_requested="pydanticai",
        engine_requested="agentsociety",
        sample_count_requested=3,
        stability_runs=2,
        comparison_key="comparison-mid",
    )
    report_new = _campaign_report_with_updates(
        base_report,
        campaign_id="campaign_new",
        created_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
        topic="Topic C",
        mode=DeliberationMode.hybrid,
        runtime_requested="legacy",
        engine_requested="oasis",
        sample_count_requested=4,
        stability_runs=1,
        comparison_key="comparison-new",
    )

    _write_campaign_report(tmp_path, report_old)
    _write_campaign_report(tmp_path, report_mid)
    _write_campaign_report(tmp_path, report_new)

    comparison = compare_deliberation_campaign_reports(latest=2, output_dir=tmp_path)

    assert comparison.latest == 2
    assert comparison.summary.campaign_ids == ["campaign_new", "campaign_mid"]
    assert [entry.campaign_id for entry in comparison.entries] == ["campaign_new", "campaign_mid"]
    assert comparison.summary.comparable is False
    assert set(comparison.summary.mismatch_reasons) == {
        "topic_mismatch",
        "mode_mismatch",
        "runtime_mismatch",
        "engine_mismatch",
        "sample_count_mismatch",
        "stability_runs_mismatch",
        "comparison_key_mismatch",
    }
    assert comparison.summary.topic_values == ["Topic C", "Topic B"]
    assert comparison.summary.mode_values == [DeliberationMode.hybrid.value, DeliberationMode.simulation.value]
    assert comparison.summary.runtime_values == ["legacy", "pydanticai"]
    assert comparison.summary.engine_values == ["oasis", "agentsociety"]
    assert comparison.summary.sample_count_values == [3, 4]
    assert comparison.summary.stability_runs_values == [1, 2]
    assert comparison.summary.comparison_key_values == ["comparison-new", "comparison-mid"]
    assert comparison.summary.sample_count_requested_total == 7
    assert comparison.summary.sample_count_completed_total == 2
    assert comparison.summary.sample_count_failed_total == 0


def test_campaign_keeps_fallback_for_single_sample_when_requested() -> None:
    calls: list[dict[str, object]] = []

    def runner(**kwargs):
        calls.append(kwargs)
        return FakeResult(
            deliberation_id="delib_single",
            score=0.81,
            confidence=0.72,
            runtime_used="pydanticai",
            fallback_used=False,
        )

    report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        allow_fallback=True,
        runner=runner,
        persist=False,
    )

    assert len(calls) == 1
    assert calls[0]["allow_fallback"] is True
    assert report.fallback_guard_applied is False
    assert report.allow_fallback_effective is True
    assert report.summary.sample_count_requested == 1
    assert report.summary.sample_count_completed == 1
    assert report.summary.campaign_stability_summary is not None


def test_campaign_disables_fallback_for_intra_run_stability_repeats() -> None:
    calls: list[dict[str, object]] = []

    def runner(**kwargs):
        calls.append(kwargs)
        return FakeResult(
            deliberation_id="delib_stability",
            score=0.77,
            confidence=0.69,
            runtime_used="pydanticai",
            fallback_used=False,
        )

    report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        stability_runs=2,
        allow_fallback=True,
        runner=runner,
        persist=False,
    )

    assert len(calls) == 1
    assert calls[0]["allow_fallback"] is False
    assert calls[0]["stability_runs"] == 2
    assert report.fallback_guard_applied is True
    assert report.allow_fallback_effective is False


def test_campaign_listing_sorts_by_created_at_and_filters_status_and_limit(tmp_path) -> None:
    base_report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        allow_fallback=False,
        runner=lambda **kwargs: FakeResult(
            deliberation_id="delib_list",
            score=0.75,
            confidence=0.7,
            runtime_used="pydanticai",
            fallback_used=False,
        ),
        persist=False,
    )

    completed_report = base_report.model_copy(
        update={
            "campaign_id": "campaign_completed",
            "status": DeliberationCampaignStatus.completed,
            "created_at": datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
        }
    )
    partial_report = base_report.model_copy(
        update={
            "campaign_id": "campaign_partial",
            "status": DeliberationCampaignStatus.partial,
            "created_at": datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
        }
    )
    failed_report = base_report.model_copy(
        update={
            "campaign_id": "campaign_failed",
            "status": DeliberationCampaignStatus.failed,
            "created_at": datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
        }
    )

    _write_campaign_report(tmp_path, completed_report)
    _write_campaign_report(tmp_path, partial_report)
    _write_campaign_report(tmp_path, failed_report)
    (tmp_path / "campaign_without_report").mkdir()

    reports = list_deliberation_campaign_reports(output_dir=tmp_path)

    assert [report.campaign_id for report in reports] == [
        "campaign_partial",
        "campaign_failed",
        "campaign_completed",
    ]

    filtered = list_deliberation_campaign_reports(output_dir=tmp_path, status=DeliberationCampaignStatus.completed)
    assert [report.campaign_id for report in filtered] == ["campaign_completed"]

    limited = list_deliberation_campaign_reports(output_dir=tmp_path, limit=2)
    assert [report.campaign_id for report in limited] == ["campaign_partial", "campaign_failed"]


def test_campaign_comparison_reports_support_explicit_ids_and_latest(tmp_path) -> None:
    base_report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        allow_fallback=False,
        runner=lambda **kwargs: FakeResult(
            deliberation_id="delib_compare",
            score=0.75,
            confidence=0.7,
            runtime_used="pydanticai",
            fallback_used=False,
        ),
        persist=False,
    )

    alpha = base_report.model_copy(
        update={
            "campaign_id": "campaign_alpha",
            "created_at": datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
            "report_path": str(tmp_path / "campaign_alpha" / "report.json"),
            "summary": base_report.summary.model_copy(
                update={
                    "quality_score_mean": 0.7,
                    "quality_score_min": 0.68,
                    "quality_score_max": 0.72,
                    "confidence_level_mean": 0.71,
                    "confidence_level_min": 0.7,
                    "confidence_level_max": 0.72,
                    "runtime_counts": {"pydanticai": 1},
                    "engine_counts": {"agentsociety": 1},
                    "fallback_count": 0,
                }
            ),
        }
    )
    beta = base_report.model_copy(
        update={
            "campaign_id": "campaign_beta",
            "created_at": datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
            "report_path": str(tmp_path / "campaign_beta" / "report.json"),
            "summary": base_report.summary.model_copy(
                update={
                    "quality_score_mean": 0.82,
                    "quality_score_min": 0.8,
                    "quality_score_max": 0.84,
                    "confidence_level_mean": 0.79,
                    "confidence_level_min": 0.78,
                    "confidence_level_max": 0.8,
                    "runtime_counts": {"pydanticai": 1},
                    "engine_counts": {"agentsociety": 1},
                    "fallback_count": 0,
                }
            ),
        }
    )
    gamma = base_report.model_copy(
        update={
            "campaign_id": "campaign_gamma",
            "topic": "Plan the rollout",
            "mode": DeliberationMode.hybrid,
            "runtime_requested": "legacy",
            "engine_requested": "oasis",
            "sample_count_requested": 3,
            "stability_runs": 2,
            "fallback_guard_applied": True,
            "fallback_guard_reason": "fallback_disabled_for_repeated_campaign_comparison",
            "created_at": datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            "report_path": str(tmp_path / "campaign_gamma" / "report.json"),
            "summary": base_report.summary.model_copy(
                update={
                    "quality_score_mean": 0.61,
                    "quality_score_min": 0.6,
                    "quality_score_max": 0.62,
                    "confidence_level_mean": 0.63,
                    "confidence_level_min": 0.62,
                    "confidence_level_max": 0.64,
                    "runtime_counts": {"legacy": 1},
                    "engine_counts": {"oasis": 1},
                    "fallback_count": 1,
                }
            ),
        }
    )

    _write_campaign_report(tmp_path, alpha)
    _write_campaign_report(tmp_path, beta)
    _write_campaign_report(tmp_path, gamma)

    explicit = compare_deliberation_campaign_reports(
        campaign_ids=["campaign_alpha", "campaign_beta"],
        output_dir=tmp_path,
    )
    assert explicit.requested_campaign_ids == ["campaign_alpha", "campaign_beta"]
    assert [entry.campaign_id for entry in explicit.entries] == ["campaign_alpha", "campaign_beta"]
    assert explicit.summary.comparable is True
    assert explicit.summary.mismatch_reasons == []
    assert explicit.summary.quality_score_max == 0.82
    assert explicit.summary.campaign_ids == ["campaign_alpha", "campaign_beta"]

    latest = compare_deliberation_campaign_reports(latest=2, output_dir=tmp_path)
    assert latest.latest == 2
    assert [entry.campaign_id for entry in latest.entries] == ["campaign_gamma", "campaign_beta"]
    assert latest.summary.comparable is False
    assert "topic_mismatch" in latest.summary.mismatch_reasons
    assert "mode_mismatch" in latest.summary.mismatch_reasons
    assert "runtime_mismatch" in latest.summary.mismatch_reasons
    assert "engine_mismatch" in latest.summary.mismatch_reasons
    assert "sample_count_mismatch" in latest.summary.mismatch_reasons
    assert "stability_runs_mismatch" in latest.summary.mismatch_reasons


def test_campaign_comparison_persists_loads_and_lists_round_trip(tmp_path) -> None:
    campaigns_dir = tmp_path / "campaigns"
    comparisons_dir = tmp_path / "comparisons"

    base_report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        allow_fallback=False,
        runner=lambda **kwargs: FakeResult(
            deliberation_id="delib_persist",
            score=0.79,
            confidence=0.73,
            runtime_used="pydanticai",
            fallback_used=False,
        ),
        persist=False,
    )

    report_a = _campaign_report_with_updates(
        base_report,
        campaign_id="campaign_a",
        created_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
    )
    report_b = _campaign_report_with_updates(
        base_report,
        campaign_id="campaign_b",
        created_at=datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
    )

    _write_campaign_report(campaigns_dir, report_a)
    _write_campaign_report(campaigns_dir, report_b)

    comparison = compare_deliberation_campaign_reports(
        campaign_ids=["campaign_a", "campaign_b"],
        output_dir=campaigns_dir,
        persist=True,
        comparison_output_dir=comparisons_dir,
    )

    assert comparison.report_path is not None
    assert Path(comparison.report_path).exists()
    assert comparison.metadata["persisted"] is True

    loaded = load_deliberation_campaign_comparison_report(
        comparison.comparison_id,
        output_dir=comparisons_dir,
    )

    assert loaded.comparison_id == comparison.comparison_id
    assert loaded.requested_campaign_ids == ["campaign_a", "campaign_b"]
    assert loaded.summary.campaign_ids == ["campaign_a", "campaign_b"]
    assert loaded.report_path == comparison.report_path

    report_c = compare_deliberation_campaign_reports(
        campaign_ids=["campaign_b", "campaign_a"],
        output_dir=campaigns_dir,
        persist=True,
        comparison_output_dir=comparisons_dir,
    )

    listed = list_deliberation_campaign_comparison_reports(output_dir=comparisons_dir)

    assert [report.comparison_id for report in listed] == [report_c.comparison_id, comparison.comparison_id]
    assert listed[0].created_at >= listed[1].created_at


def test_campaign_comparison_audit_builds_structured_payload_and_markdown(tmp_path) -> None:
    base_report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        allow_fallback=False,
        runner=lambda **kwargs: FakeResult(
            deliberation_id="delib_audit",
            score=0.8,
            confidence=0.75,
            runtime_used="pydanticai",
            fallback_used=False,
        ),
        persist=False,
    )

    report_a = _campaign_report_with_updates(
        base_report,
        campaign_id="campaign_audit_a",
        created_at=datetime(2026, 4, 4, 12, 0, tzinfo=timezone.utc),
    )
    report_b = _campaign_report_with_updates(
        base_report,
        campaign_id="campaign_audit_b",
        created_at=datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc),
        topic="Compare the rollout plan",
        runtime_requested="legacy",
        engine_requested="oasis",
        sample_count_requested=2,
        stability_runs=2,
        comparison_key="comparison-audit-b",
    )

    _write_campaign_report(tmp_path, report_a)
    _write_campaign_report(tmp_path, report_b)

    comparison = compare_deliberation_campaign_reports(
        campaign_ids=["campaign_audit_a", "campaign_audit_b"],
        output_dir=tmp_path,
        persist=True,
        comparison_output_dir=tmp_path / "comparisons",
    )

    audit = build_deliberation_campaign_comparison_audit(comparison)

    assert isinstance(audit, DeliberationCampaignComparisonAudit)
    assert audit.comparison_id == comparison.comparison_id
    assert audit.campaign_count == 2
    assert audit.campaign_ids == ["campaign_audit_a", "campaign_audit_b"]
    assert audit.comparable is False
    assert "topic_mismatch" in audit.mismatch_reasons
    assert audit.metadata["entry_count"] == 2
    assert audit.markdown is not None
    assert "# Deliberation Campaign Comparison" in audit.markdown
    assert "campaign_audit_a" in audit.markdown
    assert "campaign_audit_b" in audit.markdown

    markdown = render_deliberation_campaign_comparison_markdown(audit)
    assert markdown == audit.markdown


def test_campaign_comparison_audit_loads_from_persisted_report_round_trip(tmp_path) -> None:
    campaigns_dir = tmp_path / "campaigns"
    comparisons_dir = tmp_path / "comparisons"

    base_report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        allow_fallback=False,
        runner=lambda **kwargs: FakeResult(
            deliberation_id="delib_audit_load",
            score=0.77,
            confidence=0.71,
            runtime_used="pydanticai",
            fallback_used=False,
        ),
        persist=False,
    )

    report_a = _campaign_report_with_updates(
        base_report,
        campaign_id="campaign_audit_load_a",
        created_at=datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc),
    )
    report_b = _campaign_report_with_updates(
        base_report,
        campaign_id="campaign_audit_load_b",
        created_at=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
        comparison_key="comparison-audit-load-b",
    )

    _write_campaign_report(campaigns_dir, report_a)
    _write_campaign_report(campaigns_dir, report_b)

    comparison = compare_deliberation_campaign_reports(
        campaign_ids=["campaign_audit_load_a", "campaign_audit_load_b"],
        output_dir=campaigns_dir,
        persist=True,
        comparison_output_dir=comparisons_dir,
    )

    audit = load_deliberation_campaign_comparison_audit(
        comparison.comparison_id,
        output_dir=comparisons_dir,
        include_markdown=False,
    )

    assert audit.comparison_id == comparison.comparison_id
    assert audit.report_path == comparison.report_path
    assert audit.markdown is None
    assert audit.summary.campaign_ids == ["campaign_audit_load_a", "campaign_audit_load_b"]
    assert audit.metadata["report_path"] == comparison.report_path
    assert audit.metadata["entry_count"] == 2


def test_campaign_comparison_export_materializes_round_trip(tmp_path) -> None:
    campaigns_dir = tmp_path / "campaigns"
    comparisons_dir = tmp_path / "comparisons"
    exports_dir = tmp_path / "exports"

    base_report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        allow_fallback=False,
        runner=lambda **kwargs: FakeResult(
            deliberation_id="delib_export",
            score=0.79,
            confidence=0.73,
            runtime_used="pydanticai",
            fallback_used=False,
        ),
        persist=False,
    )

    report_a = _campaign_report_with_updates(
        base_report,
        campaign_id="campaign_export_a",
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
    )
    report_b = _campaign_report_with_updates(
        base_report,
        campaign_id="campaign_export_b",
        created_at=datetime(2026, 4, 8, 13, 0, tzinfo=timezone.utc),
        comparison_key="comparison-export-b",
    )

    _write_campaign_report(campaigns_dir, report_a)
    _write_campaign_report(campaigns_dir, report_b)

    comparison = compare_deliberation_campaign_reports(
        campaign_ids=["campaign_export_a", "campaign_export_b"],
        output_dir=campaigns_dir,
        persist=True,
        comparison_output_dir=comparisons_dir,
    )

    export = materialize_deliberation_campaign_comparison_export(
        comparison,
        output_dir=exports_dir,
        format="markdown",
        export_id="campaign_compare_export_demo",
    )

    assert isinstance(export, DeliberationCampaignComparisonExport)
    assert export.export_id == "campaign_compare_export_demo"
    assert export.manifest_path is not None
    assert Path(export.manifest_path).exists()
    assert export.content_path is not None
    assert Path(export.content_path).exists()
    assert export.content is not None
    assert "# Deliberation Campaign Comparison" in export.content
    assert export.metadata["persisted"] is True

    loaded = load_deliberation_campaign_comparison_export(
        export.export_id,
        output_dir=exports_dir,
    )

    assert loaded.export_id == export.export_id
    assert loaded.manifest_path == export.manifest_path
    assert loaded.content_path == export.content_path
    assert loaded.content == export.content
    assert loaded.comparison_id == comparison.comparison_id
    assert loaded.metadata["manifest_path"] == export.manifest_path
    assert loaded.metadata["content_path"] == export.content_path

    listed = list_deliberation_campaign_comparison_exports(output_dir=exports_dir)
    assert [item.export_id for item in listed] == [export.export_id]


def test_campaign_comparison_export_listing_orders_by_created_at(tmp_path) -> None:
    exports_dir = tmp_path / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    export_older = DeliberationCampaignComparisonExport(
        export_id="campaign_compare_export_old",
        created_at=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
        output_dir=str(exports_dir),
        comparison_id="comparison_old",
        comparison_report_path="/tmp/comparisons/comparison_old/report.json",
        format="markdown",
        campaign_count=2,
        campaign_ids=["campaign_a", "campaign_b"],
        comparable=True,
        mismatch_reasons=[],
        content="# old",
        metadata={"persisted": True},
    )
    export_newer = DeliberationCampaignComparisonExport(
        export_id="campaign_compare_export_new",
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
        output_dir=str(exports_dir),
        comparison_id="comparison_new",
        comparison_report_path="/tmp/comparisons/comparison_new/report.json",
        format="json",
        campaign_count=2,
        campaign_ids=["campaign_a", "campaign_b"],
        comparable=False,
        mismatch_reasons=["comparison_key_mismatch"],
        content="{\"comparison_id\": \"comparison_new\"}",
        metadata={"persisted": True},
    )

    for export in (export_older, export_newer):
        export_dir = exports_dir / export.export_id
        export_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = export_dir / "manifest.json"
        content_path = export_dir / ("content.md" if export.format == "markdown" else "content.json")
        export.manifest_path = str(manifest_path)
        export.content_path = str(content_path)
        export.metadata["manifest_path"] = str(manifest_path)
        export.metadata["content_path"] = str(content_path)
        manifest_path.write_text(
            export.model_dump_json(indent=2, exclude={"content"}),
            encoding="utf-8",
        )
        content_path.write_text(export.content or "", encoding="utf-8")

    listed = list_deliberation_campaign_comparison_exports(output_dir=exports_dir)
    assert [item.export_id for item in listed] == [export_newer.export_id, export_older.export_id]


def test_campaign_comparison_bundle_materializes_compare_audit_export_round_trip(tmp_path) -> None:
    campaigns_dir = tmp_path / "campaigns"
    comparisons_dir = tmp_path / "comparisons"
    exports_dir = tmp_path / "exports"

    base_report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        allow_fallback=False,
        runner=lambda **kwargs: FakeResult(
            deliberation_id="delib_bundle",
            score=0.81,
            confidence=0.74,
            runtime_used="pydanticai",
            fallback_used=False,
        ),
        persist=False,
    )

    report_a = _campaign_report_with_updates(
        base_report,
        campaign_id="campaign_bundle_a",
        created_at=datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
    )
    report_b = _campaign_report_with_updates(
        base_report,
        campaign_id="campaign_bundle_b",
        created_at=datetime(2026, 4, 9, 13, 0, tzinfo=timezone.utc),
        comparison_key="comparison-bundle-b",
    )

    _write_campaign_report(campaigns_dir, report_a)
    _write_campaign_report(campaigns_dir, report_b)

    bundle = compare_deliberation_campaign_bundle(
        campaign_ids=["campaign_bundle_a", "campaign_bundle_b"],
        output_dir=campaigns_dir,
        comparison_output_dir=comparisons_dir,
        export_output_dir=exports_dir,
        format="markdown",
    )

    assert isinstance(bundle, DeliberationCampaignComparisonBundle)
    assert bundle.comparison_report.report_path is not None
    assert Path(bundle.comparison_report.report_path).exists()
    assert bundle.audit.report_path == bundle.comparison_report.report_path
    assert bundle.audit.markdown is not None
    assert bundle.export.export_id == f"{bundle.comparison_report.comparison_id}__markdown"
    assert bundle.export.manifest_path is not None
    assert Path(bundle.export.manifest_path).exists()
    assert bundle.export.content_path is not None
    assert Path(bundle.export.content_path).exists()
    assert bundle.export.content is not None
    assert "# Deliberation Campaign Comparison" in bundle.export.content
    assert bundle.metadata["campaign_ids"] == ["campaign_bundle_a", "campaign_bundle_b"]
    assert bundle.metadata["latest"] is None
    assert bundle.metadata["comparison_id"] == bundle.comparison_report.comparison_id
    assert bundle.metadata["export_id"] == bundle.export.export_id
    assert bundle.metadata["format"] == "markdown"

    loaded_export = load_deliberation_campaign_comparison_export(
        bundle.export.export_id,
        output_dir=exports_dir,
    )
    assert loaded_export.export_id == bundle.export.export_id
    assert loaded_export.content == bundle.export.content


def test_campaign_comparison_bundle_supports_latest_selection(tmp_path) -> None:
    campaigns_dir = tmp_path / "campaigns"
    comparisons_dir = tmp_path / "comparisons"
    exports_dir = tmp_path / "exports"

    base_report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        allow_fallback=False,
        runner=lambda **kwargs: FakeResult(
            deliberation_id="delib_latest",
            score=0.83,
            confidence=0.76,
            runtime_used="pydanticai",
            fallback_used=False,
        ),
        persist=False,
    )

    reports = [
        _campaign_report_with_updates(
            base_report,
            campaign_id="campaign_latest_a",
            created_at=datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
        ),
        _campaign_report_with_updates(
            base_report,
            campaign_id="campaign_latest_b",
            created_at=datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
            comparison_key="comparison-latest-b",
        ),
        _campaign_report_with_updates(
            base_report,
            campaign_id="campaign_latest_c",
            created_at=datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc),
            comparison_key="comparison-latest-c",
        ),
    ]
    for report in reports:
        _write_campaign_report(campaigns_dir, report)

    bundle = compare_deliberation_campaign_bundle(
        latest=2,
        output_dir=campaigns_dir,
        comparison_output_dir=comparisons_dir,
        export_output_dir=exports_dir,
        format="json",
    )

    assert isinstance(bundle, DeliberationCampaignComparisonBundle)
    assert bundle.comparison_report.latest == 2
    assert bundle.comparison_report.summary.campaign_count == 2
    assert bundle.audit.markdown is None
    assert bundle.export.format == "json"
    assert bundle.export.export_id == f"{bundle.comparison_report.comparison_id}__json"
    assert bundle.export.content_path is not None
    assert Path(bundle.export.content_path).exists()
    assert bundle.export.manifest_path is not None
    assert Path(bundle.export.manifest_path).exists()
    assert bundle.export.content is not None
    assert "\"comparison_id\"" in bundle.export.content
    assert bundle.metadata["campaign_ids"] == []
    assert bundle.metadata["latest"] == 2
    assert bundle.metadata["comparison_id"] == bundle.comparison_report.comparison_id
    assert bundle.metadata["export_id"] == bundle.export.export_id
    assert bundle.metadata["format"] == "json"


def test_campaign_benchmark_runs_baseline_and_candidate_then_materializes_bundle(monkeypatch, tmp_path) -> None:
    run_calls: list[dict[str, object]] = []
    compare_calls: list[dict[str, object]] = []

    def fake_runner(**kwargs):
        run_calls.append(kwargs)
        return SimpleNamespace(campaign_id=kwargs["campaign_id"])

    bundle_payload = {
        "comparison_report": {
            "comparison_id": "benchmark_compare_demo",
            "created_at": "2026-04-08T12:00:00+00:00",
            "output_dir": str(tmp_path / "campaigns"),
            "report_path": str(tmp_path / "comparisons" / "benchmark_compare_demo" / "report.json"),
            "requested_campaign_ids": ["benchmark_baseline_demo", "benchmark_candidate_demo"],
            "latest": None,
            "entries": [],
            "summary": {
                "campaign_count": 2,
                "campaign_ids": ["benchmark_baseline_demo", "benchmark_candidate_demo"],
                "status_counts": {"completed": 2},
                "topic_values": ["Choose the launch strategy"],
                "mode_values": ["committee"],
                "runtime_values": ["legacy", "pydanticai"],
                "engine_values": ["agentsociety", "oasis"],
                "sample_count_values": [3],
                "stability_runs_values": [2],
                "comparison_key_values": ["comparison-key-demo"],
                "comparable": True,
                "mismatch_reasons": [],
                "quality_score_mean": 0.76,
                "quality_score_min": 0.72,
                "quality_score_max": 0.8,
                "confidence_level_mean": 0.71,
                "confidence_level_min": 0.68,
                "confidence_level_max": 0.74,
                "sample_count_requested_total": 6,
                "sample_count_completed_total": 6,
                "sample_count_failed_total": 0,
            },
            "metadata": {"comparison_key": "comparison-key-demo"},
        },
        "audit": {
            "comparison_id": "benchmark_compare_demo",
            "created_at": "2026-04-08T12:05:00+00:00",
            "output_dir": str(tmp_path / "comparisons"),
            "report_path": str(tmp_path / "comparisons" / "benchmark_compare_demo" / "report.json"),
            "requested_campaign_ids": ["benchmark_baseline_demo", "benchmark_candidate_demo"],
            "latest": None,
            "campaign_count": 2,
            "campaign_ids": ["benchmark_baseline_demo", "benchmark_candidate_demo"],
            "comparable": True,
            "mismatch_reasons": [],
            "entries": [],
            "summary": {
                "campaign_count": 2,
                "campaign_ids": ["benchmark_baseline_demo", "benchmark_candidate_demo"],
                "status_counts": {"completed": 2},
                "topic_values": ["Choose the launch strategy"],
                "mode_values": ["committee"],
                "runtime_values": ["legacy", "pydanticai"],
                "engine_values": ["agentsociety", "oasis"],
                "sample_count_values": [3],
                "stability_runs_values": [2],
                "comparison_key_values": ["comparison-key-demo"],
                "comparable": True,
                "mismatch_reasons": [],
                "quality_score_mean": 0.76,
                "quality_score_min": 0.72,
                "quality_score_max": 0.8,
                "confidence_level_mean": 0.71,
                "confidence_level_min": 0.68,
                "confidence_level_max": 0.74,
                "sample_count_requested_total": 6,
                "sample_count_completed_total": 6,
                "sample_count_failed_total": 0,
            },
            "markdown": "# Deliberation Campaign Comparison\n\n- Comparison ID: benchmark_compare_demo\n",
            "metadata": {"comparison_key": "comparison-key-demo"},
        },
        "export": {
            "export_id": "benchmark_compare_demo__markdown",
            "created_at": "2026-04-08T12:10:00+00:00",
            "output_dir": str(tmp_path / "exports"),
            "manifest_path": str(tmp_path / "exports" / "benchmark_compare_demo__markdown" / "manifest.json"),
            "content_path": str(tmp_path / "exports" / "benchmark_compare_demo__markdown" / "content.md"),
            "comparison_id": "benchmark_compare_demo",
            "comparison_report_path": str(tmp_path / "comparisons" / "benchmark_compare_demo" / "report.json"),
            "format": "markdown",
            "campaign_count": 2,
            "campaign_ids": ["benchmark_baseline_demo", "benchmark_candidate_demo"],
            "comparable": True,
            "mismatch_reasons": [],
            "content": "# Deliberation Campaign Comparison\n\n- Comparison ID: benchmark_compare_demo\n",
            "metadata": {"persisted": True},
        },
    }

    def fake_compare_deliberation_campaign_bundle(**kwargs):
        compare_calls.append(kwargs)
        return type("Bundle", (), {"model_dump": lambda self, mode="json": bundle_payload})()

    monkeypatch.setattr("swarm_core.deliberation_campaign.compare_deliberation_campaign_bundle", fake_compare_deliberation_campaign_bundle)

    bundle = run_deliberation_campaign_benchmark_sync(
        topic="Choose the launch strategy",
        sample_count=3,
        stability_runs=2,
        baseline_runtime="pydanticai",
        candidate_runtime="legacy",
        baseline_engine_preference="agentsociety",
        candidate_engine_preference="oasis",
        output_dir=tmp_path / "campaigns",
        comparison_output_dir=tmp_path / "comparisons",
        export_output_dir=tmp_path / "exports",
        benchmark_output_dir=tmp_path / "benchmarks",
        format="markdown",
        baseline_campaign_id="benchmark_baseline_demo",
        candidate_campaign_id="benchmark_candidate_demo",
        runner=fake_runner,
    )

    assert isinstance(bundle, DeliberationCampaignBenchmarkBundle)
    assert len(run_calls) == 6
    assert all(call["runtime"] == "pydanticai" for call in run_calls[:3])
    assert all(call["runtime"] == "legacy" for call in run_calls[3:])
    assert all(call["engine_preference"].value == "agentsociety" for call in run_calls[:3])
    assert all(call["engine_preference"].value == "oasis" for call in run_calls[3:])
    assert compare_calls[0]["campaign_ids"] == ["benchmark_baseline_demo", "benchmark_candidate_demo"]
    assert compare_calls[0]["persist"] is True
    assert str(compare_calls[0]["comparison_output_dir"]).endswith("comparisons")
    assert str(compare_calls[0]["export_output_dir"]).endswith("exports")
    assert compare_calls[0]["format"] == "markdown"
    assert bundle.baseline_campaign.campaign_id == "benchmark_baseline_demo"
    assert bundle.candidate_campaign.campaign_id == "benchmark_candidate_demo"
    assert bundle.comparison_bundle.comparison_report.comparison_id == "benchmark_compare_demo"
    assert bundle.comparison_bundle.export.export_id == "benchmark_compare_demo__markdown"
    assert bundle.benchmark_id == "benchmark_baseline_demo__vs__benchmark_candidate_demo"
    assert bundle.created_at.tzinfo is not None
    assert bundle.output_dir == str(tmp_path / "benchmarks")
    assert bundle.report_path is not None
    assert Path(bundle.report_path).exists()
    assert bundle.metadata["baseline_runtime"] == "pydanticai"
    assert bundle.metadata["candidate_runtime"] == "legacy"
    assert bundle.metadata["baseline_engine_preference"] == "agentsociety"
    assert bundle.metadata["candidate_engine_preference"] == "oasis"
    assert bundle.metadata["comparison_id"] == "benchmark_compare_demo"
    assert bundle.metadata["export_id"] == "benchmark_compare_demo__markdown"
    assert bundle.metadata["benchmark_id"] == bundle.benchmark_id
    assert bundle.metadata["benchmark_output_dir"] == str(tmp_path / "benchmarks")
    assert bundle.metadata["report_path"] == bundle.report_path

    loaded = load_deliberation_campaign_benchmark(bundle.benchmark_id, output_dir=tmp_path / "benchmarks")
    assert loaded.benchmark_id == bundle.benchmark_id
    assert loaded.comparison_bundle.comparison_report.comparison_id == "benchmark_compare_demo"
    listed = list_deliberation_campaign_benchmarks(output_dir=tmp_path / "benchmarks")
    assert [item.benchmark_id for item in listed] == [bundle.benchmark_id]


def test_campaign_benchmark_generates_default_ids(monkeypatch, tmp_path) -> None:
    run_calls: list[dict[str, object]] = []
    compare_calls: list[dict[str, object]] = []
    uuids = iter(["abc12345deadbeef", "fedcba9876543210"])

    def fake_uuid4():
        return SimpleNamespace(hex=next(uuids))

    def fake_runner(**kwargs):
        run_calls.append(kwargs)
        return SimpleNamespace(campaign_id=kwargs["campaign_id"])

    def fake_compare_deliberation_campaign_bundle(**kwargs):
        compare_calls.append(kwargs)
        payload = {
            "comparison_report": {
                "comparison_id": "benchmark_compare_default",
                "created_at": "2026-04-08T12:00:00+00:00",
                "output_dir": str(tmp_path / "campaigns"),
                "report_path": str(tmp_path / "comparisons" / "benchmark_compare_default" / "report.json"),
                "requested_campaign_ids": [kwargs["campaign_ids"][0], kwargs["campaign_ids"][1]],
                "latest": None,
                "entries": [],
                "summary": {
                    "campaign_count": 2,
                    "campaign_ids": [kwargs["campaign_ids"][0], kwargs["campaign_ids"][1]],
                    "status_counts": {"completed": 2},
                    "topic_values": ["Choose the launch strategy"],
                    "mode_values": ["committee"],
                    "runtime_values": ["legacy", "pydanticai"],
                    "engine_values": ["agentsociety", "oasis"],
                    "sample_count_values": [1],
                    "stability_runs_values": [1],
                    "comparison_key_values": ["comparison-key-default"],
                    "comparable": True,
                    "mismatch_reasons": [],
                    "quality_score_mean": 0.75,
                    "quality_score_min": 0.7,
                    "quality_score_max": 0.8,
                    "confidence_level_mean": 0.7,
                    "confidence_level_min": 0.65,
                    "confidence_level_max": 0.75,
                    "sample_count_requested_total": 2,
                    "sample_count_completed_total": 2,
                    "sample_count_failed_total": 0,
                },
                "metadata": {"comparison_key": "comparison-key-default"},
            },
            "audit": {
                "comparison_id": "benchmark_compare_default",
                "created_at": "2026-04-08T12:05:00+00:00",
                "output_dir": str(tmp_path / "comparisons"),
                "report_path": str(tmp_path / "comparisons" / "benchmark_compare_default" / "report.json"),
                "requested_campaign_ids": [kwargs["campaign_ids"][0], kwargs["campaign_ids"][1]],
                "latest": None,
                "campaign_count": 2,
                "campaign_ids": [kwargs["campaign_ids"][0], kwargs["campaign_ids"][1]],
                "comparable": True,
                "mismatch_reasons": [],
                "entries": [],
                "summary": {
                    "campaign_count": 2,
                    "campaign_ids": [kwargs["campaign_ids"][0], kwargs["campaign_ids"][1]],
                    "status_counts": {"completed": 2},
                    "topic_values": ["Choose the launch strategy"],
                    "mode_values": ["committee"],
                    "runtime_values": ["legacy", "pydanticai"],
                    "engine_values": ["agentsociety", "oasis"],
                    "sample_count_values": [1],
                    "stability_runs_values": [1],
                    "comparison_key_values": ["comparison-key-default"],
                    "comparable": True,
                    "mismatch_reasons": [],
                    "quality_score_mean": 0.75,
                    "quality_score_min": 0.7,
                    "quality_score_max": 0.8,
                    "confidence_level_mean": 0.7,
                    "confidence_level_min": 0.65,
                    "confidence_level_max": 0.75,
                    "sample_count_requested_total": 2,
                    "sample_count_completed_total": 2,
                    "sample_count_failed_total": 0,
                },
                "markdown": "# Deliberation Campaign Comparison\n\n- Comparison ID: benchmark_compare_default\n",
                "metadata": {"comparison_key": "comparison-key-default"},
            },
            "export": {
                "export_id": "benchmark_compare_default__json",
                "created_at": "2026-04-08T12:10:00+00:00",
                "output_dir": str(tmp_path / "exports"),
                "manifest_path": str(tmp_path / "exports" / "benchmark_compare_default__json" / "manifest.json"),
                "content_path": str(tmp_path / "exports" / "benchmark_compare_default__json" / "content.json"),
                "comparison_id": "benchmark_compare_default",
                "comparison_report_path": str(tmp_path / "comparisons" / "benchmark_compare_default" / "report.json"),
                "format": "json",
                "campaign_count": 2,
                "campaign_ids": [kwargs["campaign_ids"][0], kwargs["campaign_ids"][1]],
                "comparable": True,
                "mismatch_reasons": [],
                "content": "{\"comparison_id\": \"benchmark_compare_default\"}",
                "metadata": {"persisted": True},
            },
        }
        return type("Bundle", (), {"model_dump": lambda self, mode="json": payload})()

    monkeypatch.setattr("swarm_core.deliberation_campaign.uuid4", fake_uuid4)
    monkeypatch.setattr("swarm_core.deliberation_campaign.compare_deliberation_campaign_bundle", fake_compare_deliberation_campaign_bundle)

    bundle = run_deliberation_campaign_benchmark_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        stability_runs=1,
        output_dir=tmp_path / "campaigns",
        comparison_output_dir=tmp_path / "comparisons",
        export_output_dir=tmp_path / "exports",
        benchmark_output_dir=tmp_path / "benchmarks",
        format="json",
        runner=fake_runner,
    )

    assert bundle.baseline_campaign.campaign_id == "benchmark_baseline_abc12345dead"
    assert bundle.candidate_campaign.campaign_id == "benchmark_candidate_fedcba987654"
    assert len(run_calls) == 2
    assert compare_calls[0]["campaign_ids"] == [
        "benchmark_baseline_abc12345dead",
        "benchmark_candidate_fedcba987654",
    ]
    assert bundle.metadata["campaign_ids"] == [
        "benchmark_baseline_abc12345dead",
        "benchmark_candidate_fedcba987654",
    ]
    assert bundle.metadata["format"] == "json"
    assert bundle.metadata["persisted"] is True
    assert bundle.report_path is not None
    assert Path(bundle.report_path).exists()


def test_campaign_benchmark_listing_orders_by_created_at(monkeypatch, tmp_path) -> None:
    def fake_runner(**kwargs):
        return SimpleNamespace(campaign_id=kwargs["campaign_id"])

    def fake_compare_deliberation_campaign_bundle(**kwargs):
        baseline_id, candidate_id = kwargs["campaign_ids"]
        comparison_id = f"{baseline_id}__vs__{candidate_id}"
        payload = {
            "comparison_report": {
                "comparison_id": comparison_id,
                "created_at": "2026-04-08T12:00:00+00:00",
                "output_dir": str(tmp_path / "campaigns"),
                "report_path": str(tmp_path / "comparisons" / comparison_id / "report.json"),
                "requested_campaign_ids": [baseline_id, candidate_id],
                "latest": None,
                "entries": [],
                "summary": {
                    "campaign_count": 2,
                    "campaign_ids": [baseline_id, candidate_id],
                    "status_counts": {"completed": 2},
                    "topic_values": ["Choose the launch strategy"],
                    "mode_values": ["committee"],
                    "runtime_values": ["legacy", "pydanticai"],
                    "engine_values": ["agentsociety", "oasis"],
                    "sample_count_values": [1],
                    "stability_runs_values": [1],
                    "comparison_key_values": ["comparison-key-list"],
                    "comparable": True,
                    "mismatch_reasons": [],
                    "quality_score_mean": 0.75,
                    "quality_score_min": 0.7,
                    "quality_score_max": 0.8,
                    "confidence_level_mean": 0.7,
                    "confidence_level_min": 0.65,
                    "confidence_level_max": 0.75,
                    "sample_count_requested_total": 2,
                    "sample_count_completed_total": 2,
                    "sample_count_failed_total": 0,
                },
                "metadata": {"comparison_key": "comparison-key-list"},
            },
            "audit": {
                "comparison_id": comparison_id,
                "created_at": "2026-04-08T12:05:00+00:00",
                "output_dir": str(tmp_path / "comparisons"),
                "report_path": str(tmp_path / "comparisons" / comparison_id / "report.json"),
                "requested_campaign_ids": [baseline_id, candidate_id],
                "latest": None,
                "campaign_count": 2,
                "campaign_ids": [baseline_id, candidate_id],
                "comparable": True,
                "mismatch_reasons": [],
                "entries": [],
                "summary": {
                    "campaign_count": 2,
                    "campaign_ids": [baseline_id, candidate_id],
                    "status_counts": {"completed": 2},
                    "topic_values": ["Choose the launch strategy"],
                    "mode_values": ["committee"],
                    "runtime_values": ["legacy", "pydanticai"],
                    "engine_values": ["agentsociety", "oasis"],
                    "sample_count_values": [1],
                    "stability_runs_values": [1],
                    "comparison_key_values": ["comparison-key-list"],
                    "comparable": True,
                    "mismatch_reasons": [],
                    "quality_score_mean": 0.75,
                    "quality_score_min": 0.7,
                    "quality_score_max": 0.8,
                    "confidence_level_mean": 0.7,
                    "confidence_level_min": 0.65,
                    "confidence_level_max": 0.75,
                    "sample_count_requested_total": 2,
                    "sample_count_completed_total": 2,
                    "sample_count_failed_total": 0,
                },
                "markdown": "# Deliberation Campaign Comparison\n\n- Comparison ID: " + comparison_id + "\n",
                "metadata": {"comparison_key": "comparison-key-list"},
            },
            "export": {
                "export_id": f"{comparison_id}__json",
                "created_at": "2026-04-08T12:10:00+00:00",
                "output_dir": str(tmp_path / "exports"),
                "manifest_path": str(tmp_path / "exports" / f"{comparison_id}__json" / "manifest.json"),
                "content_path": str(tmp_path / "exports" / f"{comparison_id}__json" / "content.json"),
                "comparison_id": comparison_id,
                "comparison_report_path": str(tmp_path / "comparisons" / comparison_id / "report.json"),
                "format": "json",
                "campaign_count": 2,
                "campaign_ids": [baseline_id, candidate_id],
                "comparable": True,
                "mismatch_reasons": [],
                "content": "{\"comparison_id\": \"" + comparison_id + "\"}",
                "metadata": {"persisted": True},
            },
        }
        return type("Bundle", (), {"model_dump": lambda self, mode="json": payload})()

    monkeypatch.setattr("swarm_core.deliberation_campaign.compare_deliberation_campaign_bundle", fake_compare_deliberation_campaign_bundle)

    first_bundle = run_deliberation_campaign_benchmark_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        stability_runs=1,
        output_dir=tmp_path / "campaigns",
        comparison_output_dir=tmp_path / "comparisons",
        export_output_dir=tmp_path / "exports",
        benchmark_output_dir=tmp_path / "benchmarks",
        format="json",
        baseline_campaign_id="benchmark_baseline_one",
        candidate_campaign_id="benchmark_candidate_one",
        runner=fake_runner,
    )
    second_bundle = run_deliberation_campaign_benchmark_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        stability_runs=1,
        output_dir=tmp_path / "campaigns",
        comparison_output_dir=tmp_path / "comparisons",
        export_output_dir=tmp_path / "exports",
        benchmark_output_dir=tmp_path / "benchmarks",
        format="json",
        baseline_campaign_id="benchmark_baseline_two",
        candidate_campaign_id="benchmark_candidate_two",
        runner=fake_runner,
    )

    listed = list_deliberation_campaign_benchmarks(output_dir=tmp_path / "benchmarks", limit=1)
    assert [item.benchmark_id for item in listed] == [second_bundle.benchmark_id]
    assert first_bundle.benchmark_id == "benchmark_baseline_one__vs__benchmark_candidate_one"
    assert second_bundle.benchmark_id == "benchmark_baseline_two__vs__benchmark_candidate_two"
    loaded_first = load_deliberation_campaign_benchmark(
        first_bundle.benchmark_id,
        output_dir=tmp_path / "benchmarks",
    )
    assert loaded_first.benchmark_id == first_bundle.benchmark_id


def test_campaign_matrix_benchmark_runs_baseline_and_multiple_candidates_then_materializes_bundle(monkeypatch, tmp_path) -> None:
    run_calls: list[dict[str, object]] = []
    compare_calls: list[dict[str, object]] = []

    def fake_runner(**kwargs):
        run_calls.append(kwargs)
        engine_used = getattr(kwargs["engine_preference"], "value", kwargs["engine_preference"])
        score = 0.9 if kwargs["runtime"] == "pydanticai" else 0.8 if kwargs["runtime"] == "legacy" else 0.75
        confidence = 0.88 if engine_used == "agentsociety" else 0.83 if engine_used == "oasis" else 0.8
        return FakeResult(
            deliberation_id=f"{kwargs['campaign_id']}_delib",
            score=score,
            confidence=confidence,
            runtime_used=kwargs["runtime"],
            fallback_used=False,
            engine_used=engine_used,
        )

    def fake_compare_deliberation_campaign_bundle(**kwargs):
        compare_calls.append(kwargs)
        baseline_id, candidate_id = kwargs["campaign_ids"]
        comparison_id = f"{baseline_id}__vs__{candidate_id}"
        candidate_score = 0.8 if candidate_id.endswith("legacy") else 0.75
        payload = {
            "comparison_report": {
                "comparison_id": comparison_id,
                "created_at": "2026-04-08T12:00:00+00:00",
                "output_dir": str(tmp_path / "campaigns"),
                "report_path": str(tmp_path / "comparisons" / comparison_id / "report.json"),
                "requested_campaign_ids": [baseline_id, candidate_id],
                "latest": None,
                "entries": [],
                "summary": {
                    "campaign_count": 2,
                    "campaign_ids": [baseline_id, candidate_id],
                    "status_counts": {"completed": 2},
                    "topic_values": ["Choose the launch strategy"],
                    "mode_values": ["committee"],
                    "runtime_values": ["legacy", "pydanticai"],
                    "engine_values": ["agentsociety", "oasis"],
                    "sample_count_values": [2],
                    "stability_runs_values": [1],
                    "comparison_key_values": ["comparison-key-matrix"],
                    "comparable": True,
                    "mismatch_reasons": [],
                    "quality_score_mean": candidate_score,
                    "quality_score_min": candidate_score - 0.02,
                    "quality_score_max": candidate_score + 0.02,
                    "confidence_level_mean": candidate_score - 0.03,
                    "confidence_level_min": candidate_score - 0.05,
                    "confidence_level_max": candidate_score - 0.01,
                    "sample_count_requested_total": 4,
                    "sample_count_completed_total": 4,
                    "sample_count_failed_total": 0,
                },
                "metadata": {"comparison_key": "comparison-key-matrix"},
            },
            "audit": {
                "comparison_id": comparison_id,
                "created_at": "2026-04-08T12:05:00+00:00",
                "output_dir": str(tmp_path / "comparisons"),
                "report_path": str(tmp_path / "comparisons" / comparison_id / "report.json"),
                "requested_campaign_ids": [baseline_id, candidate_id],
                "latest": None,
                "campaign_count": 2,
                "campaign_ids": [baseline_id, candidate_id],
                "comparable": True,
                "mismatch_reasons": [],
                "entries": [],
                "summary": {
                    "campaign_count": 2,
                    "campaign_ids": [baseline_id, candidate_id],
                    "status_counts": {"completed": 2},
                    "topic_values": ["Choose the launch strategy"],
                    "mode_values": ["committee"],
                    "runtime_values": ["legacy", "pydanticai"],
                    "engine_values": ["agentsociety", "oasis"],
                    "sample_count_values": [2],
                    "stability_runs_values": [1],
                    "comparison_key_values": ["comparison-key-matrix"],
                    "comparable": True,
                    "mismatch_reasons": [],
                    "quality_score_mean": candidate_score,
                    "quality_score_min": candidate_score - 0.02,
                    "quality_score_max": candidate_score + 0.02,
                    "confidence_level_mean": candidate_score - 0.03,
                    "confidence_level_min": candidate_score - 0.05,
                    "confidence_level_max": candidate_score - 0.01,
                    "sample_count_requested_total": 4,
                    "sample_count_completed_total": 4,
                    "sample_count_failed_total": 0,
                },
                "markdown": "# Deliberation Campaign Comparison\n\n- Comparison ID: " + comparison_id + "\n",
                "metadata": {"comparison_key": "comparison-key-matrix"},
            },
            "export": {
                "export_id": f"{comparison_id}__json",
                "created_at": "2026-04-08T12:10:00+00:00",
                "output_dir": str(tmp_path / "exports"),
                "manifest_path": str(tmp_path / "exports" / f"{comparison_id}__json" / "manifest.json"),
                "content_path": str(tmp_path / "exports" / f"{comparison_id}__json" / "content.json"),
                "comparison_id": comparison_id,
                "comparison_report_path": str(tmp_path / "comparisons" / comparison_id / "report.json"),
                "format": "json",
                "campaign_count": 2,
                "campaign_ids": [baseline_id, candidate_id],
                "comparable": True,
                "mismatch_reasons": [],
                "content": "{\"comparison_id\": \"" + comparison_id + "\"}",
                "metadata": {"persisted": True},
            },
        }
        return type("Bundle", (), {"model_dump": lambda self, mode="json": payload})()

    monkeypatch.setattr("swarm_core.deliberation_campaign.compare_deliberation_campaign_bundle", fake_compare_deliberation_campaign_bundle)

    bundle = run_deliberation_campaign_matrix_benchmark_sync(
        topic="Choose the launch strategy",
        sample_count=2,
        stability_runs=1,
        baseline_runtime="pydanticai",
        baseline_engine_preference="agentsociety",
        candidate_specs=[
            DeliberationCampaignMatrixCandidateSpec(
                label="Legacy candidate",
                campaign_id="matrix_candidate_legacy",
                runtime="legacy",
                engine_preference="oasis",
            ),
            DeliberationCampaignMatrixCandidateSpec(
                label="Hybrid candidate",
                campaign_id="matrix_candidate_hybrid",
                runtime="hybrid",
                engine_preference="agentsociety",
            ),
        ],
        output_dir=tmp_path / "campaigns",
        comparison_output_dir=tmp_path / "comparisons",
        export_output_dir=tmp_path / "exports",
        benchmark_output_dir=tmp_path / "matrix_benchmarks",
        format="json",
        benchmark_id="matrix_benchmark_demo",
        baseline_campaign_id="matrix_baseline_demo",
        runner=fake_runner,
    )

    assert isinstance(bundle, DeliberationCampaignMatrixBenchmarkBundle)
    assert len(run_calls) == 6
    assert {call["runtime"] for call in run_calls} == {"pydanticai", "legacy", "hybrid"}
    assert compare_calls[0]["campaign_ids"] == ["matrix_baseline_demo", "matrix_candidate_legacy"]
    assert compare_calls[1]["campaign_ids"] == ["matrix_baseline_demo", "matrix_candidate_hybrid"]
    assert bundle.benchmark_id == "matrix_benchmark_demo"
    assert bundle.baseline_campaign.campaign_id == "matrix_baseline_demo"
    assert [spec.campaign_id for spec in bundle.candidate_specs] == [
        "matrix_candidate_legacy",
        "matrix_candidate_hybrid",
    ]
    assert [entry.candidate_label for entry in bundle.entries] == [
        "Legacy candidate",
        "Hybrid candidate",
    ]
    assert bundle.summary.candidate_count == 2
    assert bundle.summary.candidate_campaign_ids == [
        "matrix_candidate_legacy",
        "matrix_candidate_hybrid",
    ]
    assert bundle.summary.comparison_ids == [
        "matrix_baseline_demo__vs__matrix_candidate_legacy",
        "matrix_baseline_demo__vs__matrix_candidate_hybrid",
    ]
    assert bundle.summary.comparable_count == 2
    assert bundle.summary.mismatch_count == 0
    assert bundle.summary.status_counts == {"comparable": 2}
    assert bundle.metadata["candidate_count"] == 2
    assert bundle.metadata["campaign_ids"] == [
        "matrix_baseline_demo",
        "matrix_candidate_legacy",
        "matrix_candidate_hybrid",
    ]
    assert bundle.report_path is not None
    assert Path(bundle.report_path).exists()

    loaded = load_deliberation_campaign_matrix_benchmark(bundle.benchmark_id, output_dir=tmp_path / "matrix_benchmarks")
    assert loaded.benchmark_id == bundle.benchmark_id
    assert loaded.summary.candidate_count == 2
    listed = list_deliberation_campaign_matrix_benchmarks(output_dir=tmp_path / "matrix_benchmarks")
    assert [item.benchmark_id for item in listed] == [bundle.benchmark_id]


def test_matrix_benchmark_comparison_loads_explicit_reports_and_aggregates_homogeneous_metrics(tmp_path) -> None:
    base_report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        allow_fallback=False,
        runner=lambda **kwargs: FakeResult(
            deliberation_id="delib_matrix_compare",
            score=0.79,
            confidence=0.74,
            runtime_used="pydanticai",
            fallback_used=False,
        ),
        persist=False,
    )

    candidate_specs = [
        DeliberationCampaignMatrixCandidateSpec(
            label="Legacy candidate",
            campaign_id="matrix_candidate_legacy",
            runtime="legacy",
            engine_preference="oasis",
        ),
        DeliberationCampaignMatrixCandidateSpec(
            label="Hybrid candidate",
            campaign_id="matrix_candidate_hybrid",
            runtime="hybrid",
            engine_preference="agentsociety",
        ),
    ]
    benchmark_a = _matrix_benchmark_bundle_with_updates(
        base_report,
        benchmark_id="matrix_compare_a",
        created_at=datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc),
        candidate_specs=candidate_specs,
        quality_score_mean=0.78,
        confidence_level_mean=0.72,
    )
    benchmark_b = _matrix_benchmark_bundle_with_updates(
        base_report,
        benchmark_id="matrix_compare_b",
        created_at=datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc),
        candidate_specs=candidate_specs,
        quality_score_mean=0.82,
        confidence_level_mean=0.77,
    )

    _write_matrix_benchmark_report(tmp_path, benchmark_a)
    _write_matrix_benchmark_report(tmp_path, benchmark_b)

    comparison = compare_deliberation_campaign_matrix_benchmarks(
        benchmark_ids=["matrix_compare_a", "matrix_compare_b"],
        output_dir=tmp_path,
    )

    assert isinstance(comparison, DeliberationCampaignMatrixBenchmarkComparisonReport)
    assert comparison.requested_benchmark_ids == ["matrix_compare_a", "matrix_compare_b"]
    assert [entry.benchmark_id for entry in comparison.entries] == ["matrix_compare_a", "matrix_compare_b"]
    assert comparison.summary.benchmark_count == 2
    assert comparison.summary.benchmark_ids == ["matrix_compare_a", "matrix_compare_b"]
    assert comparison.summary.comparable is True
    assert comparison.summary.mismatch_reasons == []
    assert comparison.summary.topic_values == ["Choose the launch strategy"]
    assert comparison.summary.mode_values == [DeliberationMode.committee.value]
    assert comparison.summary.baseline_runtime_values == ["pydanticai"]
    assert comparison.summary.baseline_engine_values == ["agentsociety"]
    assert comparison.summary.runtime_values == ["pydanticai", "legacy", "hybrid"]
    assert comparison.summary.engine_values == ["agentsociety", "oasis"]
    assert comparison.summary.sample_count_values == [1]
    assert comparison.summary.stability_runs_values == [1]
    assert comparison.summary.candidate_count_values == [2]
    assert len(comparison.summary.candidate_structure_key_values) == 1
    assert comparison.summary.candidate_count_total == 4


def test_matrix_benchmark_comparison_latest_flags_mismatches_and_uses_latest_n(tmp_path) -> None:
    base_report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        allow_fallback=False,
        runner=lambda **kwargs: FakeResult(
            deliberation_id="delib_matrix_latest",
            score=0.8,
            confidence=0.75,
            runtime_used="pydanticai",
            fallback_used=False,
        ),
        persist=False,
    )

    benchmark_old = _matrix_benchmark_bundle_with_updates(
        base_report,
        benchmark_id="matrix_old",
        created_at=datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc),
        topic="Topic Old",
        mode=DeliberationMode.committee,
        baseline_runtime="legacy",
        baseline_engine="agentsociety",
        sample_count_requested=2,
        stability_runs=3,
        candidate_specs=[
            DeliberationCampaignMatrixCandidateSpec(
                label="Legacy only",
                campaign_id="matrix_old_candidate",
                runtime="legacy",
                engine_preference="oasis",
            )
        ],
        mismatch_count=1,
        comparable_count=0,
    )
    benchmark_mid = _matrix_benchmark_bundle_with_updates(
        base_report,
        benchmark_id="matrix_mid",
        created_at=datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc),
        topic="Topic Mid",
        mode=DeliberationMode.simulation,
        baseline_runtime="pydanticai",
        baseline_engine="agentsociety",
        sample_count_requested=3,
        stability_runs=2,
        candidate_specs=[
            DeliberationCampaignMatrixCandidateSpec(
                label="Legacy candidate",
                campaign_id="matrix_mid_candidate_legacy",
                runtime="legacy",
                engine_preference="oasis",
            )
        ],
        mismatch_count=1,
        comparable_count=0,
    )
    benchmark_new = _matrix_benchmark_bundle_with_updates(
        base_report,
        benchmark_id="matrix_new",
        created_at=datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc),
        topic="Topic New",
        mode=DeliberationMode.hybrid,
        baseline_runtime="legacy",
        baseline_engine="oasis",
        sample_count_requested=4,
        stability_runs=1,
        candidate_specs=[
            DeliberationCampaignMatrixCandidateSpec(
                label="Legacy candidate",
                campaign_id="matrix_new_candidate_legacy",
                runtime="legacy",
                engine_preference="oasis",
            ),
            DeliberationCampaignMatrixCandidateSpec(
                label="Hybrid candidate",
                campaign_id="matrix_new_candidate_hybrid",
                runtime="hybrid",
                engine_preference="agentsociety",
            ),
        ],
        mismatch_count=2,
        comparable_count=0,
    )

    _write_matrix_benchmark_report(tmp_path, benchmark_old)
    _write_matrix_benchmark_report(tmp_path, benchmark_mid)
    _write_matrix_benchmark_report(tmp_path, benchmark_new)

    comparison = compare_deliberation_campaign_matrix_benchmarks(latest=2, output_dir=tmp_path)

    assert comparison.latest == 2
    assert comparison.summary.benchmark_ids == ["matrix_new", "matrix_mid"]
    assert [entry.benchmark_id for entry in comparison.entries] == ["matrix_new", "matrix_mid"]
    assert comparison.summary.comparable is False
    assert set(comparison.summary.mismatch_reasons) == {
        "topic_mismatch",
        "mode_mismatch",
        "baseline_runtime_mismatch",
        "baseline_engine_mismatch",
        "sample_count_mismatch",
        "stability_runs_mismatch",
        "candidate_count_mismatch",
        "candidate_structure_mismatch",
    }


def test_matrix_benchmark_comparison_persists_loads_and_lists_round_trip(tmp_path) -> None:
    benchmarks_dir = tmp_path / "matrix_benchmarks"
    comparisons_dir = tmp_path / "matrix_comparisons"
    base_report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        allow_fallback=False,
        runner=lambda **kwargs: FakeResult(
            deliberation_id="delib_matrix_persist",
            score=0.81,
            confidence=0.76,
            runtime_used="pydanticai",
            fallback_used=False,
        ),
        persist=False,
    )

    benchmark_a = _matrix_benchmark_bundle_with_updates(
        base_report,
        benchmark_id="matrix_persist_a",
        created_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
    )
    benchmark_b = _matrix_benchmark_bundle_with_updates(
        base_report,
        benchmark_id="matrix_persist_b",
        created_at=datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
    )

    _write_matrix_benchmark_report(benchmarks_dir, benchmark_a)
    _write_matrix_benchmark_report(benchmarks_dir, benchmark_b)

    comparison = compare_deliberation_campaign_matrix_benchmarks(
        benchmark_ids=["matrix_persist_a", "matrix_persist_b"],
        output_dir=benchmarks_dir,
        persist=True,
        comparison_output_dir=comparisons_dir,
    )

    assert comparison.report_path is not None
    assert Path(comparison.report_path).exists()
    assert comparison.metadata["persisted"] is True

    loaded = load_deliberation_campaign_matrix_benchmark_comparison_report(
        comparison.comparison_id,
        output_dir=comparisons_dir,
    )
    assert loaded.comparison_id == comparison.comparison_id
    assert loaded.requested_benchmark_ids == ["matrix_persist_a", "matrix_persist_b"]
    assert loaded.summary.benchmark_ids == ["matrix_persist_a", "matrix_persist_b"]

    comparison_newer = compare_deliberation_campaign_matrix_benchmarks(
        benchmark_ids=["matrix_persist_b", "matrix_persist_a"],
        output_dir=benchmarks_dir,
        persist=True,
        comparison_output_dir=comparisons_dir,
    )
    listed = list_deliberation_campaign_matrix_benchmark_comparison_reports(output_dir=comparisons_dir)
    assert [report.comparison_id for report in listed] == [comparison_newer.comparison_id, comparison.comparison_id]


def test_matrix_benchmark_comparison_audit_export_bundle_round_trip(tmp_path) -> None:
    benchmarks_dir = tmp_path / "matrix_benchmarks"
    comparisons_dir = tmp_path / "matrix_comparisons"
    exports_dir = tmp_path / "matrix_exports"
    base_report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        allow_fallback=False,
        runner=lambda **kwargs: FakeResult(
            deliberation_id="delib_matrix_audit",
            score=0.82,
            confidence=0.77,
            runtime_used="pydanticai",
            fallback_used=False,
        ),
        persist=False,
    )

    benchmark_a = _matrix_benchmark_bundle_with_updates(
        base_report,
        benchmark_id="matrix_audit_a",
        created_at=datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc),
    )
    benchmark_b = _matrix_benchmark_bundle_with_updates(
        base_report,
        benchmark_id="matrix_audit_b",
        created_at=datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
    )

    _write_matrix_benchmark_report(benchmarks_dir, benchmark_a)
    _write_matrix_benchmark_report(benchmarks_dir, benchmark_b)

    comparison = compare_deliberation_campaign_matrix_benchmarks(
        benchmark_ids=["matrix_audit_a", "matrix_audit_b"],
        output_dir=benchmarks_dir,
        persist=True,
        comparison_output_dir=comparisons_dir,
    )

    audit = build_deliberation_campaign_matrix_benchmark_comparison_audit(comparison)
    assert isinstance(audit, DeliberationCampaignMatrixBenchmarkComparisonAudit)
    assert audit.comparison_id == comparison.comparison_id
    assert audit.report_path == comparison.report_path
    assert audit.markdown is not None
    assert "# Deliberation Campaign Matrix Benchmark Comparison" in audit.markdown
    assert audit.metadata["report_path"] == comparison.report_path
    assert audit.metadata["entry_count"] == 2

    loaded_audit = load_deliberation_campaign_matrix_benchmark_comparison_audit(
        comparison.comparison_id,
        output_dir=comparisons_dir,
    )
    assert loaded_audit.comparison_id == comparison.comparison_id
    assert loaded_audit.markdown is not None
    assert loaded_audit.summary.benchmark_ids == ["matrix_audit_a", "matrix_audit_b"]

    export = materialize_deliberation_campaign_matrix_benchmark_comparison_export(
        audit,
        output_dir=exports_dir,
        format="markdown",
        export_id="matrix_compare_export_demo",
    )
    assert isinstance(export, DeliberationCampaignMatrixBenchmarkComparisonExport)
    assert export.export_id == "matrix_compare_export_demo"
    assert export.manifest_path is not None
    assert Path(export.manifest_path).exists()
    assert export.content_path is not None
    assert Path(export.content_path).exists()
    assert export.content is not None
    assert "# Deliberation Campaign Matrix Benchmark Comparison" in export.content
    assert export.metadata["persisted"] is True

    loaded_export = load_deliberation_campaign_matrix_benchmark_comparison_export(
        export.export_id,
        output_dir=exports_dir,
    )
    assert loaded_export.export_id == export.export_id
    assert loaded_export.manifest_path == export.manifest_path
    assert loaded_export.content_path == export.content_path
    assert loaded_export.content == export.content
    assert loaded_export.comparison_id == comparison.comparison_id
    assert loaded_export.metadata["manifest_path"] == export.manifest_path
    assert loaded_export.metadata["content_path"] == export.content_path

    listed_exports = list_deliberation_campaign_matrix_benchmark_comparison_exports(output_dir=exports_dir)
    assert [item.export_id for item in listed_exports] == [export.export_id]

    bundle = compare_deliberation_campaign_matrix_benchmark_comparison_bundle(
        benchmark_ids=["matrix_audit_a", "matrix_audit_b"],
        output_dir=benchmarks_dir,
        comparison_output_dir=comparisons_dir,
        export_output_dir=exports_dir,
        format="json",
    )
    assert isinstance(bundle, DeliberationCampaignMatrixBenchmarkComparisonBundle)
    assert bundle.comparison_report.report_path is not None
    assert Path(bundle.comparison_report.report_path).exists()
    assert bundle.audit.report_path == bundle.comparison_report.report_path
    assert bundle.audit.markdown is None
    assert bundle.export.export_id == f"{bundle.comparison_report.comparison_id}__json"
    assert bundle.export.manifest_path is not None
    assert Path(bundle.export.manifest_path).exists()
    assert bundle.export.content_path is not None
    assert Path(bundle.export.content_path).exists()
    assert bundle.export.content is not None
    assert "\"comparison_id\"" in bundle.export.content
    assert bundle.metadata["benchmark_ids"] == ["matrix_audit_a", "matrix_audit_b"]
    assert bundle.metadata["latest"] is None
    assert bundle.metadata["comparison_id"] == bundle.comparison_report.comparison_id
    assert bundle.metadata["export_id"] == bundle.export.export_id
    assert bundle.metadata["format"] == "json"


def test_matrix_benchmark_export_comparison_audit_export_bundle_round_trip(tmp_path) -> None:
    benchmarks_dir = tmp_path / "matrix_benchmarks"
    exports_dir = tmp_path / "matrix_exports"
    comparison_reports_dir = tmp_path / "matrix_export_comparisons"
    comparison_exports_dir = tmp_path / "matrix_export_comparison_exports"
    base_report = run_deliberation_campaign_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        allow_fallback=False,
        runner=lambda **kwargs: FakeResult(
            deliberation_id="delib_matrix_export_compare",
            score=0.79,
            confidence=0.74,
            runtime_used="pydanticai",
            fallback_used=False,
        ),
        persist=False,
    )

    benchmark_a = _matrix_benchmark_bundle_with_updates(
        base_report,
        benchmark_id="matrix_export_compare_a",
        created_at=datetime(2026, 4, 16, 10, 0, tzinfo=timezone.utc),
    )
    benchmark_b = _matrix_benchmark_bundle_with_updates(
        base_report,
        benchmark_id="matrix_export_compare_b",
        created_at=datetime(2026, 4, 17, 10, 0, tzinfo=timezone.utc),
    )

    _write_matrix_benchmark_report(benchmarks_dir, benchmark_a)
    _write_matrix_benchmark_report(benchmarks_dir, benchmark_b)

    export_a = materialize_deliberation_campaign_matrix_benchmark_export(
        benchmark_a,
        output_dir=exports_dir,
        format="markdown",
        export_id="matrix_export_compare_a__markdown",
    )
    export_b = materialize_deliberation_campaign_matrix_benchmark_export(
        benchmark_b,
        output_dir=exports_dir,
        format="json",
        export_id="matrix_export_compare_b__json",
    )

    comparison = compare_deliberation_campaign_matrix_benchmark_exports(
        export_ids=[export_a.export_id, export_b.export_id],
        output_dir=exports_dir,
        persist=True,
        comparison_output_dir=comparison_reports_dir,
    )
    assert isinstance(comparison, DeliberationCampaignMatrixBenchmarkExportComparisonReport)
    assert comparison.summary.export_count == 2
    assert comparison.summary.format_values == ["markdown", "json"]
    assert comparison.summary.comparable is True

    loaded = load_deliberation_campaign_matrix_benchmark_export_comparison_report(
        comparison.comparison_id,
        output_dir=comparison_reports_dir,
    )
    assert loaded.comparison_id == comparison.comparison_id
    assert loaded.summary.export_ids == [export_a.export_id, export_b.export_id]

    listed = list_deliberation_campaign_matrix_benchmark_export_comparison_reports(
        output_dir=comparison_reports_dir
    )
    assert [item.comparison_id for item in listed] == [comparison.comparison_id]

    audit = build_deliberation_campaign_matrix_benchmark_export_comparison_audit(comparison)
    assert isinstance(audit, DeliberationCampaignMatrixBenchmarkExportComparisonAudit)
    assert audit.comparison_id == comparison.comparison_id
    assert audit.markdown is not None
    assert "# Deliberation Campaign Matrix Benchmark Export Comparison" in audit.markdown

    loaded_audit = load_deliberation_campaign_matrix_benchmark_export_comparison_audit(
        comparison.comparison_id,
        output_dir=comparison_reports_dir,
    )
    assert loaded_audit.comparison_id == comparison.comparison_id
    assert loaded_audit.summary.export_count == 2

    export = materialize_deliberation_campaign_matrix_benchmark_export_comparison_export(
        audit,
        output_dir=comparison_exports_dir,
        format="markdown",
        export_id="matrix_export_compare_bundle__markdown",
    )
    assert isinstance(export, DeliberationCampaignMatrixBenchmarkExportComparisonExport)
    assert export.export_id == "matrix_export_compare_bundle__markdown"
    assert export.manifest_path is not None
    assert Path(export.manifest_path).exists()
    assert export.content_path is not None
    assert Path(export.content_path).exists()
    assert export.content is not None
    assert "# Deliberation Campaign Matrix Benchmark Export Comparison" in export.content

    loaded_export = load_deliberation_campaign_matrix_benchmark_export_comparison_export(
        export.export_id,
        output_dir=comparison_exports_dir,
    )
    assert loaded_export.export_id == export.export_id
    assert loaded_export.content == export.content

    listed_exports = list_deliberation_campaign_matrix_benchmark_export_comparison_exports(
        output_dir=comparison_exports_dir
    )
    assert [item.export_id for item in listed_exports] == [export.export_id]

    bundle = compare_deliberation_campaign_matrix_benchmark_export_comparison_bundle(
        export_ids=[export_a.export_id, export_b.export_id],
        output_dir=exports_dir,
        comparison_output_dir=comparison_reports_dir,
        export_output_dir=comparison_exports_dir,
        format="json",
    )
    assert isinstance(bundle, DeliberationCampaignMatrixBenchmarkExportComparisonBundle)
    assert bundle.comparison_report.report_path is not None
    assert Path(bundle.comparison_report.report_path).exists()
    assert bundle.audit.report_path == bundle.comparison_report.report_path
    assert bundle.export.export_id == f"{bundle.comparison_report.comparison_id}__json"
    assert bundle.export.content is not None
    assert "\"comparison_id\"" in bundle.export.content


def test_matrix_benchmark_audit_ranks_candidates_and_round_trips_exports(monkeypatch, tmp_path) -> None:
    run_calls: list[dict[str, object]] = []
    compare_calls: list[dict[str, object]] = []

    def fake_runner(**kwargs):
        run_calls.append(kwargs)
        engine_used = getattr(kwargs["engine_preference"], "value", kwargs["engine_preference"])
        score = 0.8 if kwargs["runtime"] == "legacy" else 0.75
        confidence = 0.84 if engine_used == "oasis" else 0.81
        return FakeResult(
            deliberation_id=f"{kwargs['campaign_id']}_delib",
            score=score,
            confidence=confidence,
            runtime_used=kwargs["runtime"],
            fallback_used=False,
            engine_used=engine_used,
        )

    def fake_compare_deliberation_campaign_bundle(**kwargs):
        compare_calls.append(kwargs)
        baseline_id, candidate_id = kwargs["campaign_ids"]
        comparison_id = f"{baseline_id}__vs__{candidate_id}"
        candidate_score = 0.8 if candidate_id.endswith("legacy") else 0.75
        payload = {
            "comparison_report": {
                "comparison_id": comparison_id,
                "created_at": "2026-04-08T12:00:00+00:00",
                "output_dir": str(tmp_path / "campaigns"),
                "report_path": str(tmp_path / "comparisons" / comparison_id / "report.json"),
                "requested_campaign_ids": [baseline_id, candidate_id],
                "latest": None,
                "entries": [],
                "summary": {
                    "campaign_count": 2,
                    "campaign_ids": [baseline_id, candidate_id],
                    "status_counts": {"completed": 2},
                    "topic_values": ["Choose the launch strategy"],
                    "mode_values": ["committee"],
                    "runtime_values": ["legacy", "pydanticai"],
                    "engine_values": ["agentsociety", "oasis"],
                    "sample_count_values": [1],
                    "stability_runs_values": [1],
                    "comparison_key_values": ["comparison-key-matrix"],
                    "comparable": True,
                    "mismatch_reasons": [],
                    "quality_score_mean": candidate_score,
                    "quality_score_min": candidate_score - 0.02,
                    "quality_score_max": candidate_score + 0.02,
                    "confidence_level_mean": candidate_score - 0.03,
                    "confidence_level_min": candidate_score - 0.05,
                    "confidence_level_max": candidate_score - 0.01,
                    "sample_count_requested_total": 2,
                    "sample_count_completed_total": 2,
                    "sample_count_failed_total": 0,
                },
                "metadata": {"comparison_key": "comparison-key-matrix"},
            },
            "audit": {
                "comparison_id": comparison_id,
                "created_at": "2026-04-08T12:05:00+00:00",
                "output_dir": str(tmp_path / "comparisons"),
                "report_path": str(tmp_path / "comparisons" / comparison_id / "report.json"),
                "requested_campaign_ids": [baseline_id, candidate_id],
                "latest": None,
                "campaign_count": 2,
                "campaign_ids": [baseline_id, candidate_id],
                "comparable": True,
                "mismatch_reasons": [],
                "entries": [],
                "summary": {
                    "campaign_count": 2,
                    "campaign_ids": [baseline_id, candidate_id],
                    "status_counts": {"completed": 2},
                    "topic_values": ["Choose the launch strategy"],
                    "mode_values": ["committee"],
                    "runtime_values": ["legacy", "pydanticai"],
                    "engine_values": ["agentsociety", "oasis"],
                    "sample_count_values": [1],
                    "stability_runs_values": [1],
                    "comparison_key_values": ["comparison-key-matrix"],
                    "comparable": True,
                    "mismatch_reasons": [],
                    "quality_score_mean": candidate_score,
                    "quality_score_min": candidate_score - 0.02,
                    "quality_score_max": candidate_score + 0.02,
                    "confidence_level_mean": candidate_score - 0.03,
                    "confidence_level_min": candidate_score - 0.05,
                    "confidence_level_max": candidate_score - 0.01,
                    "sample_count_requested_total": 2,
                    "sample_count_completed_total": 2,
                    "sample_count_failed_total": 0,
                },
                "markdown": "# Deliberation Campaign Comparison\n\n- Comparison ID: " + comparison_id + "\n",
                "metadata": {"comparison_key": "comparison-key-matrix"},
            },
            "export": {
                "export_id": f"{comparison_id}__json",
                "created_at": "2026-04-08T12:10:00+00:00",
                "output_dir": str(tmp_path / "exports"),
                "manifest_path": str(tmp_path / "exports" / f"{comparison_id}__json" / "manifest.json"),
                "content_path": str(tmp_path / "exports" / f"{comparison_id}__json" / "content.json"),
                "comparison_id": comparison_id,
                "comparison_report_path": str(tmp_path / "comparisons" / comparison_id / "report.json"),
                "format": "json",
                "campaign_count": 2,
                "campaign_ids": [baseline_id, candidate_id],
                "comparable": True,
                "mismatch_reasons": [],
                "content": "{\"comparison_id\": \"" + comparison_id + "\"}",
                "metadata": {"persisted": True},
            },
        }
        return type("Bundle", (), {"model_dump": lambda self, mode="json": payload})()

    monkeypatch.setattr("swarm_core.deliberation_campaign.compare_deliberation_campaign_bundle", fake_compare_deliberation_campaign_bundle)

    benchmark = run_deliberation_campaign_matrix_benchmark_sync(
        topic="Choose the launch strategy",
        sample_count=1,
        stability_runs=1,
        baseline_runtime="pydanticai",
        baseline_engine_preference="agentsociety",
        candidate_specs=[
            DeliberationCampaignMatrixCandidateSpec(
                label="Legacy candidate",
                campaign_id="matrix_audit_ranked__legacy",
                runtime="legacy",
                engine_preference="oasis",
            ),
            DeliberationCampaignMatrixCandidateSpec(
                label="Hybrid candidate",
                campaign_id="matrix_audit_ranked__hybrid",
                runtime="hybrid",
                engine_preference="agentsociety",
            ),
        ],
        output_dir=tmp_path / "campaigns",
        comparison_output_dir=tmp_path / "comparisons",
        export_output_dir=tmp_path / "exports",
        benchmark_output_dir=tmp_path / "matrix_benchmarks",
        format="json",
        benchmark_id="matrix_audit_ranked",
        baseline_campaign_id="matrix_audit_ranked__baseline",
        runner=fake_runner,
    )

    assert len(run_calls) == 3
    assert compare_calls[0]["campaign_ids"] == ["matrix_audit_ranked__baseline", "matrix_audit_ranked__legacy"]
    assert compare_calls[1]["campaign_ids"] == ["matrix_audit_ranked__baseline", "matrix_audit_ranked__hybrid"]

    audit = build_deliberation_campaign_matrix_benchmark_audit(benchmark)
    assert isinstance(audit, DeliberationCampaignMatrixBenchmarkAudit)
    assert audit.benchmark_id == "matrix_audit_ranked"
    assert audit.summary.candidate_count == 2
    assert audit.summary.best_candidate_rank == 1
    assert audit.summary.best_candidate_label == "Legacy candidate"
    assert audit.summary.worst_candidate_rank == 2
    assert audit.summary.worst_candidate_label == "Hybrid candidate"
    assert [entry.rank for entry in audit.entries] == [1, 2]
    assert [entry.candidate_label for entry in audit.entries] == ["Legacy candidate", "Hybrid candidate"]
    assert audit.markdown is not None
    assert "# Deliberation Campaign Matrix Benchmark Audit" in audit.markdown
    assert "Candidate Ranking" in audit.markdown

    loaded_audit = load_deliberation_campaign_matrix_benchmark_audit(
        "matrix_audit_ranked",
        output_dir=tmp_path / "matrix_benchmarks",
    )
    assert loaded_audit.summary.best_candidate_label == "Legacy candidate"
    assert loaded_audit.summary.worst_candidate_label == "Hybrid candidate"
    assert loaded_audit.entries[0].rank == 1

    listed_audits = list_deliberation_campaign_matrix_benchmark_audits(
        output_dir=tmp_path / "matrix_benchmarks",
    )
    assert [item.benchmark_id for item in listed_audits] == ["matrix_audit_ranked"]

    export = build_deliberation_campaign_matrix_benchmark_export(audit, format="json")
    assert isinstance(export, DeliberationCampaignMatrixBenchmarkExport)
    assert export.benchmark_id == "matrix_audit_ranked"
    assert export.candidate_count == 2
    assert export.best_candidate_label == "Legacy candidate"
    assert export.worst_candidate_label == "Hybrid candidate"
    assert export.content is not None
    assert "\"benchmark_id\": \"matrix_audit_ranked\"" in export.content

    materialized = materialize_deliberation_campaign_matrix_benchmark_export(
        audit,
        output_dir=tmp_path / "matrix_exports",
        format="markdown",
        export_id="matrix_audit_ranked__markdown",
    )
    assert materialized.export_id == "matrix_audit_ranked__markdown"
    assert materialized.manifest_path is not None
    assert Path(materialized.manifest_path).exists()
    assert materialized.content_path is not None
    assert Path(materialized.content_path).exists()
    assert materialized.content is not None
    assert "# Deliberation Campaign Matrix Benchmark Audit" in materialized.content

    loaded_export = load_deliberation_campaign_matrix_benchmark_export(
        materialized.export_id,
        output_dir=tmp_path / "matrix_exports",
    )
    assert loaded_export.export_id == materialized.export_id
    assert loaded_export.content_path == materialized.content_path
    assert loaded_export.content == materialized.content

    listed_exports = list_deliberation_campaign_matrix_benchmark_exports(
        output_dir=tmp_path / "matrix_exports",
    )
    assert [item.export_id for item in listed_exports] == [materialized.export_id]


def test_campaign_artifact_index_uses_list_helpers_and_limits_overviews(monkeypatch, tmp_path) -> None:
    calls: dict[str, list[dict[str, object]]] = {
        "campaigns": [],
        "comparisons": [],
        "exports": [],
        "benchmarks": [],
        "matrix_benchmark_exports": [],
        "matrix_benchmark_comparisons": [],
        "matrix_benchmark_comparison_exports": [],
    }

    campaign_items = [
        SimpleNamespace(
            campaign_id="campaign_new",
            status=SimpleNamespace(value="completed"),
            created_at=datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
            topic="Topic New",
            objective="Objective New",
            mode=SimpleNamespace(value=DeliberationMode.committee.value),
            runtime_requested="pydanticai",
            engine_requested="agentsociety",
            sample_count_requested=3,
            summary=SimpleNamespace(sample_count_completed=3, sample_count_failed=0),
            fallback_guard_applied=False,
            fallback_guard_reason=None,
            report_path="/tmp/campaign_new/report.json",
            summary_metadata={"comparison_key": "cmp-new"},
            metadata={"comparison_key": "cmp-new"},
        ),
        SimpleNamespace(
            campaign_id="campaign_old",
            status=SimpleNamespace(value="partial"),
            created_at=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
            topic="Topic Old",
            objective="Objective Old",
            mode=SimpleNamespace(value=DeliberationMode.simulation.value),
            runtime_requested="legacy",
            engine_requested="oasis",
            sample_count_requested=2,
            summary=SimpleNamespace(sample_count_completed=1, sample_count_failed=1),
            fallback_guard_applied=True,
            fallback_guard_reason="fallback_disabled_for_repeated_campaign_comparison",
            report_path="/tmp/campaign_old/report.json",
            metadata={"comparison_key": "cmp-old"},
        ),
    ]
    comparison_items = [
        SimpleNamespace(
            comparison_id="comparison_new",
            created_at=datetime(2026, 4, 8, 13, 0, tzinfo=timezone.utc),
            latest=None,
            requested_campaign_ids=["campaign_new", "campaign_old"],
            summary=SimpleNamespace(
                campaign_count=2,
                campaign_ids=["campaign_new", "campaign_old"],
                comparable=False,
                mismatch_reasons=["runtime_mismatch"],
                comparison_key_values=["cmp-new", "cmp-old"],
            ),
            metadata={"comparison_key": "cmp-new"},
            report_path="/tmp/comparisons/comparison_new/report.json",
        ),
        SimpleNamespace(
            comparison_id="comparison_old",
            created_at=datetime(2026, 4, 7, 13, 0, tzinfo=timezone.utc),
            latest=2,
            requested_campaign_ids=["campaign_old", "campaign_new"],
            summary=SimpleNamespace(
                campaign_count=2,
                campaign_ids=["campaign_old", "campaign_new"],
                comparable=True,
                mismatch_reasons=[],
                comparison_key_values=["cmp-old"],
            ),
            metadata={"comparison_key": "cmp-old"},
            report_path="/tmp/comparisons/comparison_old/report.json",
        ),
    ]
    export_items = [
        SimpleNamespace(
            export_id="comparison_new__markdown",
            created_at=datetime(2026, 4, 8, 14, 0, tzinfo=timezone.utc),
            output_dir=str(tmp_path / "exports"),
            comparison_id="comparison_new",
            comparison_report_path="/tmp/comparisons/comparison_new/report.json",
            format="markdown",
            campaign_count=2,
            campaign_ids=["campaign_new", "campaign_old"],
            comparable=False,
            mismatch_reasons=["runtime_mismatch"],
            manifest_path="/tmp/exports/comparison_new__markdown/manifest.json",
            content_path="/tmp/exports/comparison_new__markdown/content.md",
        ),
        SimpleNamespace(
            export_id="comparison_old__json",
            created_at=datetime(2026, 4, 7, 14, 0, tzinfo=timezone.utc),
            output_dir=str(tmp_path / "exports"),
            comparison_id="comparison_old",
            comparison_report_path="/tmp/comparisons/comparison_old/report.json",
            format="json",
            campaign_count=2,
            campaign_ids=["campaign_old", "campaign_new"],
            comparable=True,
            mismatch_reasons=[],
            manifest_path="/tmp/exports/comparison_old__json/manifest.json",
            content_path="/tmp/exports/comparison_old__json/content.json",
        ),
    ]
    benchmark_items = [
        SimpleNamespace(
            benchmark_id="benchmark_new",
            created_at=datetime(2026, 4, 8, 15, 0, tzinfo=timezone.utc),
            output_dir=str(tmp_path / "benchmarks"),
            report_path="/tmp/benchmarks/benchmark_new/report.json",
            baseline_campaign=SimpleNamespace(campaign_id="benchmark_baseline_new"),
            candidate_campaign=SimpleNamespace(campaign_id="benchmark_candidate_new"),
            comparison_bundle=SimpleNamespace(
                comparison_report=SimpleNamespace(
                    comparison_id="benchmark_comparison_new",
                    report_path="/tmp/comparisons/benchmark_comparison_new/report.json",
                ),
                audit=SimpleNamespace(report_path="/tmp/comparisons/benchmark_comparison_new/report.json"),
                export=SimpleNamespace(
                    export_id="benchmark_comparison_new__json",
                    format="json",
                    manifest_path="/tmp/exports/benchmark_comparison_new__json/manifest.json",
                    content_path="/tmp/exports/benchmark_comparison_new__json/content.json",
                ),
            ),
        ),
        SimpleNamespace(
            benchmark_id="benchmark_old",
            created_at=datetime(2026, 4, 7, 15, 0, tzinfo=timezone.utc),
            output_dir=str(tmp_path / "benchmarks"),
            report_path="/tmp/benchmarks/benchmark_old/report.json",
            baseline_campaign=SimpleNamespace(campaign_id="benchmark_baseline_old"),
            candidate_campaign=SimpleNamespace(campaign_id="benchmark_candidate_old"),
            comparison_bundle=SimpleNamespace(
                comparison_report=SimpleNamespace(
                    comparison_id="benchmark_comparison_old",
                    report_path="/tmp/comparisons/benchmark_comparison_old/report.json",
                ),
                audit=SimpleNamespace(report_path="/tmp/comparisons/benchmark_comparison_old/report.json"),
                export=SimpleNamespace(
                    export_id="benchmark_comparison_old__markdown",
                    format="markdown",
                    manifest_path="/tmp/exports/benchmark_comparison_old__markdown/manifest.json",
                    content_path="/tmp/exports/benchmark_comparison_old__markdown/content.md",
                ),
            ),
        ),
    ]
    matrix_benchmark_comparison_export_items = [
        SimpleNamespace(
            export_id="matrix_comparison_new__markdown",
            created_at=datetime(2026, 4, 8, 16, 0, tzinfo=timezone.utc),
            output_dir=str(tmp_path / "matrix_benchmark_comparison_exports"),
            comparison_id="matrix_comparison_new",
            comparison_report_path="/tmp/matrix_comparisons/matrix_comparison_new/report.json",
            format="markdown",
            benchmark_count=2,
            benchmark_ids=["matrix_new", "matrix_old"],
            comparable=True,
            mismatch_reasons=[],
            manifest_path="/tmp/matrix_benchmark_comparison_exports/matrix_comparison_new__markdown/manifest.json",
            content_path="/tmp/matrix_benchmark_comparison_exports/matrix_comparison_new__markdown/content.md",
        )
    ]
    matrix_benchmark_export_items = [
        SimpleNamespace(
            export_id="matrix_ready_audit__markdown",
            created_at=datetime(2026, 4, 8, 15, 30, tzinfo=timezone.utc),
            output_dir=str(tmp_path / "matrix_benchmark_exports"),
            benchmark_id="benchmark_ready",
            benchmark_report_path="/tmp/benchmarks/benchmark_ready/report.json",
            format="markdown",
            candidate_count=1,
            candidate_labels=["Legacy candidate"],
            candidate_campaign_ids=["benchmark_candidate_ready"],
            comparison_ids=["benchmark_baseline_ready__vs__benchmark_candidate_ready"],
            comparable=True,
            comparable_count=1,
            mismatch_count=0,
            mismatch_reasons=[],
            quality_score_mean=0.82,
            confidence_level_mean=0.88,
            best_candidate_label="Legacy candidate",
            worst_candidate_label="Legacy candidate",
            manifest_path="/tmp/matrix_benchmark_exports/matrix_ready_audit__markdown/manifest.json",
            content_path="/tmp/matrix_benchmark_exports/matrix_ready_audit__markdown/content.md",
        )
    ]

    def fake_list_deliberation_campaign_reports(**kwargs):
        calls["campaigns"].append(kwargs)
        return campaign_items[: kwargs["limit"]]

    def fake_list_deliberation_campaign_comparison_reports(**kwargs):
        calls["comparisons"].append(kwargs)
        return comparison_items[: kwargs["limit"]]

    def fake_list_deliberation_campaign_comparison_exports(**kwargs):
        calls["exports"].append(kwargs)
        return export_items[: kwargs["limit"]]

    def fake_list_deliberation_campaign_benchmarks(**kwargs):
        calls["benchmarks"].append(kwargs)
        return benchmark_items[: kwargs["limit"]]

    def fake_list_deliberation_campaign_matrix_benchmark_exports(**kwargs):
        calls["matrix_benchmark_exports"].append(kwargs)
        return matrix_benchmark_export_items[: kwargs["limit"]]

    def fake_list_deliberation_campaign_matrix_benchmark_comparison_reports(**kwargs):
        calls["matrix_benchmark_comparisons"].append(kwargs)
        return []

    def fake_list_deliberation_campaign_matrix_benchmark_comparison_exports(**kwargs):
        calls["matrix_benchmark_comparison_exports"].append(kwargs)
        return matrix_benchmark_comparison_export_items[: kwargs["limit"]]

    monkeypatch.setattr("swarm_core.deliberation_campaign.list_deliberation_campaign_reports", fake_list_deliberation_campaign_reports)
    monkeypatch.setattr(
        "swarm_core.deliberation_campaign.list_deliberation_campaign_comparison_reports",
        fake_list_deliberation_campaign_comparison_reports,
    )
    monkeypatch.setattr(
        "swarm_core.deliberation_campaign.list_deliberation_campaign_comparison_exports",
        fake_list_deliberation_campaign_comparison_exports,
    )
    monkeypatch.setattr("swarm_core.deliberation_campaign.list_deliberation_campaign_benchmarks", fake_list_deliberation_campaign_benchmarks)
    monkeypatch.setattr(
        "swarm_core.deliberation_campaign.list_deliberation_campaign_matrix_benchmark_exports",
        fake_list_deliberation_campaign_matrix_benchmark_exports,
    )
    monkeypatch.setattr(
        "swarm_core.deliberation_campaign.list_deliberation_campaign_matrix_benchmark_comparison_reports",
        fake_list_deliberation_campaign_matrix_benchmark_comparison_reports,
    )
    monkeypatch.setattr(
        "swarm_core.deliberation_campaign.list_deliberation_campaign_matrix_benchmark_comparison_exports",
        fake_list_deliberation_campaign_matrix_benchmark_comparison_exports,
    )

    index = build_deliberation_campaign_artifact_index(
        campaign_output_dir=tmp_path / "campaigns",
        comparison_output_dir=tmp_path / "comparisons",
        export_output_dir=tmp_path / "exports",
        benchmark_output_dir=tmp_path / "benchmarks",
        matrix_benchmark_output_dir=tmp_path / "matrix_benchmarks",
        matrix_benchmark_export_output_dir=tmp_path / "matrix_benchmark_exports",
        matrix_benchmark_comparison_output_dir=tmp_path / "matrix_benchmark_comparisons",
        matrix_benchmark_comparison_export_output_dir=tmp_path / "matrix_benchmark_comparison_exports",
        limit=1,
    )

    assert isinstance(index, DeliberationCampaignArtifactIndex)
    assert index.output_dirs == {
        "campaigns": str(tmp_path / "campaigns"),
        "comparisons": str(tmp_path / "comparisons"),
        "exports": str(tmp_path / "exports"),
        "benchmarks": str(tmp_path / "benchmarks"),
        "matrix_benchmarks": str(tmp_path / "matrix_benchmarks"),
        "matrix_benchmark_exports": str(tmp_path / "matrix_benchmark_exports"),
        "matrix_benchmark_export_comparisons": str(
            Path("/home/jul/swarm/data/deliberation_campaign_matrix_benchmark_export_comparisons")
        ),
        "matrix_benchmark_export_comparison_exports": str(
            Path("/home/jul/swarm/data/deliberation_campaign_matrix_benchmark_export_comparison_exports")
        ),
        "matrix_benchmark_comparisons": str(tmp_path / "matrix_benchmark_comparisons"),
        "matrix_benchmark_comparison_exports": str(tmp_path / "matrix_benchmark_comparison_exports"),
    }
    assert index.counts == {
        "campaigns": 1,
        "comparisons": 1,
        "exports": 1,
        "benchmarks": 1,
        "matrix_benchmarks": 0,
        "matrix_benchmark_exports": 1,
        "matrix_benchmark_export_comparisons": 0,
        "matrix_benchmark_export_comparison_exports": 0,
        "matrix_benchmark_comparisons": 0,
        "matrix_benchmark_comparison_exports": 1,
    }
    assert index.campaigns[0]["campaign_id"] == "campaign_new"
    assert index.comparisons[0]["comparison_id"] == "comparison_new"
    assert index.exports[0]["export_id"] == "comparison_new__markdown"
    assert index.benchmarks[0]["benchmark_id"] == "benchmark_new"
    assert index.matrix_benchmark_exports[0]["export_id"] == "matrix_ready_audit__markdown"
    assert index.matrix_benchmark_comparison_exports[0]["export_id"] == "matrix_comparison_new__markdown"
    assert index.metadata["limit"] == 1
    assert index.metadata["artifact_count"] == 6
    assert calls["campaigns"][0]["limit"] == 1
    assert calls["comparisons"][0]["limit"] == 1
    assert calls["exports"][0]["limit"] == 1
    assert calls["benchmarks"][0]["limit"] == 1
    assert calls["matrix_benchmark_exports"][0]["limit"] == 1
    assert calls["matrix_benchmark_comparisons"][0]["limit"] == 1
    assert calls["matrix_benchmark_comparison_exports"][0]["limit"] == 1


def test_campaign_dashboard_filters_sorts_and_normalizes_rows(monkeypatch, tmp_path) -> None:
    campaign_items = [
        SimpleNamespace(
            campaign_id="campaign_completed",
            status=SimpleNamespace(value="completed"),
            created_at=datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
            topic="Topic Completed",
            objective="Objective Completed",
            mode=SimpleNamespace(value=DeliberationMode.committee.value),
            runtime_requested="pydanticai",
            engine_requested="agentsociety",
            sample_count_requested=3,
            summary=SimpleNamespace(
                sample_count_completed=3,
                sample_count_failed=0,
                quality_score_mean=0.41,
                confidence_level_mean=0.52,
                runtime_counts={"pydanticai": 2, "legacy": 1},
                engine_counts={"agentsociety": 3},
            ),
            fallback_guard_applied=False,
            fallback_guard_reason=None,
            report_path="/tmp/campaign_completed/report.json",
            metadata={"comparison_key": "cmp-completed"},
        ),
        SimpleNamespace(
            campaign_id="campaign_partial",
            status=SimpleNamespace(value="partial"),
            created_at=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
            topic="Topic Partial",
            objective="Objective Partial",
            mode=SimpleNamespace(value=DeliberationMode.simulation.value),
            runtime_requested="legacy",
            engine_requested="oasis",
            sample_count_requested=2,
            summary=SimpleNamespace(
                sample_count_completed=1,
                sample_count_failed=1,
                quality_score_mean=0.91,
                confidence_level_mean=0.21,
                runtime_counts={"legacy": 2},
                engine_counts={"oasis": 2},
            ),
            fallback_guard_applied=True,
            fallback_guard_reason="fallback_disabled_for_repeated_campaign_comparison",
            report_path="/tmp/campaign_partial/report.json",
            metadata={"comparison_key": "cmp-partial"},
        ),
    ]
    comparison_items = [
        SimpleNamespace(
            comparison_id="comparison_ready",
            created_at=datetime(2026, 4, 8, 13, 0, tzinfo=timezone.utc),
            latest=None,
            requested_campaign_ids=["campaign_completed", "campaign_partial"],
            summary=SimpleNamespace(
                campaign_count=2,
                campaign_ids=["campaign_completed", "campaign_partial"],
                comparable=True,
                mismatch_reasons=[],
                comparison_key_values=["cmp-completed"],
                runtime_values=["pydanticai"],
                engine_values=["agentsociety"],
                quality_score_mean=0.62,
                confidence_level_mean=0.71,
            ),
            metadata={"comparison_key": "cmp-completed"},
            report_path="/tmp/comparisons/comparison_ready/report.json",
        )
    ]
    export_items = [
        SimpleNamespace(
            export_id="comparison_ready__markdown",
            created_at=datetime(2026, 4, 8, 14, 0, tzinfo=timezone.utc),
            output_dir=str(tmp_path / "exports"),
            comparison_id="comparison_ready",
            comparison_report_path="/tmp/comparisons/comparison_ready/report.json",
            format="markdown",
            campaign_count=2,
            campaign_ids=["campaign_completed", "campaign_partial"],
            comparable=True,
            mismatch_reasons=[],
            manifest_path="/tmp/exports/comparison_ready__markdown/manifest.json",
            content_path="/tmp/exports/comparison_ready__markdown/content.md",
        )
    ]
    matrix_benchmark_comparison_export_items = [
        SimpleNamespace(
            export_id="matrix_comparison_ready__markdown",
            created_at=datetime(2026, 4, 8, 16, 0, tzinfo=timezone.utc),
            output_dir=str(tmp_path / "matrix_benchmark_comparison_exports"),
            comparison_id="matrix_comparison_ready",
            comparison_report_path="/tmp/matrix_comparisons/matrix_comparison_ready/report.json",
            format="markdown",
            benchmark_count=2,
            benchmark_ids=["matrix_ready_a", "matrix_ready_b"],
            comparable=True,
            mismatch_reasons=[],
            manifest_path="/tmp/matrix_benchmark_comparison_exports/matrix_comparison_ready__markdown/manifest.json",
            content_path="/tmp/matrix_benchmark_comparison_exports/matrix_comparison_ready__markdown/content.md",
        )
    ]
    matrix_benchmark_export_items = [
        SimpleNamespace(
            export_id="matrix_ready_audit__markdown",
            created_at=datetime(2026, 4, 8, 15, 30, tzinfo=timezone.utc),
            output_dir=str(tmp_path / "matrix_benchmark_exports"),
            benchmark_id="benchmark_ready",
            benchmark_report_path="/tmp/benchmarks/benchmark_ready/report.json",
            format="markdown",
            candidate_count=1,
            comparable_count=1,
            mismatch_count=0,
            best_candidate_label="Legacy candidate",
            worst_candidate_label="Legacy candidate",
            manifest_path="/tmp/matrix_benchmark_exports/matrix_ready_audit__markdown/manifest.json",
            content_path="/tmp/matrix_benchmark_exports/matrix_ready_audit__markdown/content.md",
            metadata={"quality_score_mean": 0.82, "confidence_level_mean": 0.88},
        )
    ]
    benchmark_items = [
        SimpleNamespace(
            benchmark_id="benchmark_ready",
            created_at=datetime(2026, 4, 8, 15, 0, tzinfo=timezone.utc),
            output_dir=str(tmp_path / "benchmarks"),
            report_path="/tmp/benchmarks/benchmark_ready/report.json",
            baseline_campaign=SimpleNamespace(campaign_id="benchmark_baseline_ready"),
            candidate_campaign=SimpleNamespace(campaign_id="benchmark_candidate_ready"),
            comparison_bundle=SimpleNamespace(
                comparison_report=SimpleNamespace(
                    comparison_id="benchmark_comparison_ready",
                    report_path="/tmp/comparisons/benchmark_comparison_ready/report.json",
                    summary=SimpleNamespace(
                        comparable=True,
                        quality_score_mean=0.82,
                        confidence_level_mean=0.88,
                        runtime_values=["legacy"],
                        engine_values=["agentsociety"],
                    ),
                ),
                audit=SimpleNamespace(report_path="/tmp/comparisons/benchmark_comparison_ready/report.json"),
                export=SimpleNamespace(
                    export_id="benchmark_comparison_ready__json",
                    format="json",
                    manifest_path="/tmp/exports/benchmark_comparison_ready__json/manifest.json",
                    content_path="/tmp/exports/benchmark_comparison_ready__json/content.json",
                ),
            ),
            metadata={
                "baseline_runtime": "legacy",
                "candidate_runtime": "pydanticai",
                "baseline_engine_preference": "agentsociety",
                "candidate_engine_preference": "oasis",
            },
        )
    ]

    monkeypatch.setattr(
        "swarm_core.deliberation_campaign.list_deliberation_campaign_reports",
        lambda **kwargs: campaign_items,
    )
    monkeypatch.setattr(
        "swarm_core.deliberation_campaign.list_deliberation_campaign_comparison_reports",
        lambda **kwargs: comparison_items,
    )
    monkeypatch.setattr(
        "swarm_core.deliberation_campaign.list_deliberation_campaign_comparison_exports",
        lambda **kwargs: export_items,
    )
    monkeypatch.setattr(
        "swarm_core.deliberation_campaign.list_deliberation_campaign_benchmarks",
        lambda **kwargs: benchmark_items,
    )
    monkeypatch.setattr(
        "swarm_core.deliberation_campaign.list_deliberation_campaign_matrix_benchmark_exports",
        lambda **kwargs: matrix_benchmark_export_items,
    )
    monkeypatch.setattr(
        "swarm_core.deliberation_campaign.list_deliberation_campaign_matrix_benchmark_comparison_reports",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        "swarm_core.deliberation_campaign.list_deliberation_campaign_matrix_benchmark_comparison_exports",
        lambda **kwargs: matrix_benchmark_comparison_export_items,
    )

    dashboard = build_deliberation_campaign_dashboard(
        campaign_output_dir=tmp_path / "campaigns",
        comparison_output_dir=tmp_path / "comparisons",
        export_output_dir=tmp_path / "exports",
        benchmark_output_dir=tmp_path / "benchmarks",
        matrix_benchmark_output_dir=tmp_path / "matrix_benchmarks",
        matrix_benchmark_export_output_dir=tmp_path / "matrix_benchmark_exports",
        matrix_benchmark_comparison_output_dir=tmp_path / "matrix_benchmark_comparisons",
        matrix_benchmark_comparison_export_output_dir=tmp_path / "matrix_benchmark_comparison_exports",
        kinds=["campaigns", "benchmarks"],
        limit=10,
        sort_by="quality_score_mean",
        campaign_status="completed",
        comparable_only=True,
    )

    assert isinstance(dashboard, DeliberationCampaignDashboard)
    assert dashboard.kinds == ["benchmark", "campaign"]
    assert dashboard.limit == 10
    assert dashboard.sort_by == "quality_score_mean"
    assert dashboard.campaign_status == DeliberationCampaignStatus.completed
    assert dashboard.comparable_only is True
    assert dashboard.counts == {"benchmark": 1, "campaign": 1}
    assert [row.artifact_kind for row in dashboard.rows] == ["benchmark", "campaign"]
    assert dashboard.rows[0].artifact_id == "benchmark_ready"
    assert dashboard.rows[0].quality_score_mean == 0.82
    assert dashboard.rows[0].confidence_level_mean == 0.88
    assert dashboard.rows[0].runtime_summary == "legacy, pydanticai"
    assert dashboard.rows[0].engine_summary == "agentsociety, oasis"
    assert dashboard.rows[0].artifact_path == "/tmp/benchmarks/benchmark_ready/report.json"
    assert dashboard.rows[1].artifact_id == "campaign_completed"
    assert dashboard.rows[1].status == "completed"
    assert dashboard.rows[1].comparable is True
    assert dashboard.rows[1].quality_score_mean == 0.41
    assert dashboard.rows[1].confidence_level_mean == 0.52
    assert dashboard.rows[1].runtime_summary == "pydanticai=2, legacy=1"
    assert dashboard.rows[1].engine_summary == "agentsociety=3"
    assert dashboard.rows[1].artifact_path == "/tmp/campaign_completed/report.json"
    assert dashboard.metadata["row_count"] == 2
    assert dashboard.metadata["selected_kinds"] == ["benchmark", "campaign"]
    assert dashboard.metadata["selected_status"] == "completed"
    assert dashboard.metadata["available_kinds"] == [
        "campaign",
        "comparison",
        "export",
        "benchmark",
        "matrix_benchmark",
        "matrix_benchmark_export",
        "matrix_benchmark_export_comparison",
        "matrix_benchmark_export_comparison_export",
        "matrix_benchmark_comparison",
        "matrix_benchmark_comparison_export",
    ]
    assert dashboard.metadata["matrix_benchmark_count"] == 0
    assert dashboard.metadata["matrix_benchmark_export_count"] == 1
    assert dashboard.metadata["matrix_benchmark_comparison_count"] == 0
    assert dashboard.metadata["matrix_benchmark_comparison_export_count"] == 1
    assert dashboard.metadata["source_counts"] == {
        "campaigns": 2,
        "comparisons": 1,
        "exports": 1,
        "benchmarks": 1,
        "matrix_benchmarks": 0,
        "matrix_benchmark_exports": 1,
        "matrix_benchmark_export_comparisons": 0,
        "matrix_benchmark_export_comparison_exports": 0,
        "matrix_benchmark_comparisons": 0,
        "matrix_benchmark_comparison_exports": 1,
    }
