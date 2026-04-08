from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from statistics import mean
from typing import Any, Callable
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from runtime_contracts.intent import EnginePreference

from .deliberation import DeliberationResult, run_deliberation_sync
from .deliberation_artifacts import DeliberationMode
from .deliberation_stability import DeliberationStabilitySummary


DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "deliberation_campaigns"
DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "deliberation_campaign_comparisons"
)
DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "deliberation_campaign_comparison_exports"
)
DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "deliberation_campaign_benchmarks"
)
DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "deliberation_campaign_matrix_benchmarks"
)
DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "deliberation_campaign_matrix_benchmark_comparisons"
)
DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "deliberation_campaign_matrix_benchmark_comparison_exports"
)
DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "deliberation_campaign_matrix_benchmark_exports"
)
DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "deliberation_campaign_matrix_benchmark_export_comparisons"
)
DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "deliberation_campaign_matrix_benchmark_export_comparison_exports"
)


class DeliberationCampaignStatus(str, Enum):
    completed = "completed"
    partial = "partial"
    failed = "failed"


class DeliberationCampaignSample(BaseModel):
    sample_id: str
    sample_index: int
    deliberation_id: str
    status: str
    topic: str
    objective: str
    summary: str = ""
    final_strategy: str = ""
    runtime_requested: str = ""
    runtime_used: str | None = None
    fallback_used: bool = False
    engine_requested: str | None = None
    engine_used: str | None = None
    quality_score: float = 0.0
    confidence_level: float = 0.0
    runtime_resilience: dict[str, Any] | None = None
    stability_summary: dict[str, Any] | None = None
    comparability: dict[str, Any] = Field(default_factory=dict)
    quality_warnings: list[str] = Field(default_factory=list)
    result_path: str | None = None
    error: str | None = None
    error_type: str | None = None


class DeliberationCampaignSummary(BaseModel):
    sample_count_requested: int
    sample_count_completed: int
    sample_count_failed: int
    sample_ids: list[str] = Field(default_factory=list)
    deliberation_ids: list[str] = Field(default_factory=list)
    quality_scores: list[float] = Field(default_factory=list)
    confidence_levels: list[float] = Field(default_factory=list)
    runtime_counts: dict[str, int] = Field(default_factory=dict)
    engine_counts: dict[str, int] = Field(default_factory=dict)
    status_counts: dict[str, int] = Field(default_factory=dict)
    fallback_count: int = 0
    quality_score_mean: float = 0.0
    quality_score_min: float = 0.0
    quality_score_max: float = 0.0
    confidence_level_mean: float = 0.0
    confidence_level_min: float = 0.0
    confidence_level_max: float = 0.0
    campaign_stability_summary: DeliberationStabilitySummary | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignComparisonEntry(BaseModel):
    campaign_id: str
    created_at: datetime
    status: DeliberationCampaignStatus
    topic: str
    mode: str
    runtime_requested: str
    engine_requested: str
    sample_count_requested: int
    stability_runs: int
    comparison_key: str
    sample_count_completed: int
    sample_count_failed: int
    fallback_count: int = 0
    runtime_counts: dict[str, int] = Field(default_factory=dict)
    engine_counts: dict[str, int] = Field(default_factory=dict)
    quality_score_mean: float
    quality_score_min: float
    quality_score_max: float
    confidence_level_mean: float
    confidence_level_min: float
    confidence_level_max: float
    fallback_guard_applied: bool = False
    fallback_guard_reason: str | None = None
    report_path: str | None = None


class DeliberationCampaignComparisonSummary(BaseModel):
    campaign_count: int
    campaign_ids: list[str] = Field(default_factory=list)
    status_counts: dict[str, int] = Field(default_factory=dict)
    topic_values: list[str] = Field(default_factory=list)
    mode_values: list[str] = Field(default_factory=list)
    runtime_values: list[str] = Field(default_factory=list)
    engine_values: list[str] = Field(default_factory=list)
    sample_count_values: list[int] = Field(default_factory=list)
    stability_runs_values: list[int] = Field(default_factory=list)
    comparison_key_values: list[str] = Field(default_factory=list)
    comparable: bool = True
    mismatch_reasons: list[str] = Field(default_factory=list)
    quality_score_mean: float = 0.0
    quality_score_min: float = 0.0
    quality_score_max: float = 0.0
    confidence_level_mean: float = 0.0
    confidence_level_min: float = 0.0
    confidence_level_max: float = 0.0
    sample_count_requested_total: int = 0
    sample_count_completed_total: int = 0
    sample_count_failed_total: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignComparisonReport(BaseModel):
    comparison_id: str = Field(default_factory=lambda: f"campaign_compare_{uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    output_dir: str
    report_path: str | None = None
    requested_campaign_ids: list[str] = Field(default_factory=list)
    latest: int | None = None
    entries: list[DeliberationCampaignComparisonEntry] = Field(default_factory=list)
    summary: DeliberationCampaignComparisonSummary
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignComparisonAudit(BaseModel):
    comparison_id: str
    created_at: datetime
    output_dir: str
    report_path: str | None = None
    requested_campaign_ids: list[str] = Field(default_factory=list)
    latest: int | None = None
    campaign_count: int
    campaign_ids: list[str] = Field(default_factory=list)
    comparable: bool = True
    mismatch_reasons: list[str] = Field(default_factory=list)
    entries: list[DeliberationCampaignComparisonEntry] = Field(default_factory=list)
    summary: DeliberationCampaignComparisonSummary
    markdown: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignComparisonExport(BaseModel):
    export_id: str = Field(default_factory=lambda: f"campaign_compare_export_{uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    output_dir: str
    manifest_path: str | None = None
    content_path: str | None = None
    comparison_id: str
    comparison_report_path: str | None = None
    format: str = "markdown"
    campaign_count: int
    campaign_ids: list[str] = Field(default_factory=list)
    comparable: bool = True
    mismatch_reasons: list[str] = Field(default_factory=list)
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignComparisonBundle(BaseModel):
    comparison_report: DeliberationCampaignComparisonReport
    audit: DeliberationCampaignComparisonAudit
    export: DeliberationCampaignComparisonExport
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignBenchmarkBundle(BaseModel):
    benchmark_id: str = Field(default_factory=lambda: f"campaign_benchmark_{uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    output_dir: str = Field(default_factory=lambda: str(DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR))
    report_path: str | None = None
    baseline_campaign: DeliberationCampaignReport
    candidate_campaign: DeliberationCampaignReport
    comparison_bundle: DeliberationCampaignComparisonBundle
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixCandidateSpec(BaseModel):
    label: str | None = None
    campaign_id: str | None = None
    runtime: str = "legacy"
    engine_preference: EnginePreference | str = EnginePreference.oasis
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixComparisonEntry(BaseModel):
    candidate_index: int
    candidate_label: str
    candidate_spec: DeliberationCampaignMatrixCandidateSpec
    candidate_campaign: DeliberationCampaignReport
    comparison_bundle: DeliberationCampaignComparisonBundle
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixBenchmarkSummary(BaseModel):
    candidate_count: int
    candidate_labels: list[str] = Field(default_factory=list)
    candidate_campaign_ids: list[str] = Field(default_factory=list)
    comparison_ids: list[str] = Field(default_factory=list)
    comparable_count: int = 0
    mismatch_count: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    runtime_values: list[str] = Field(default_factory=list)
    engine_values: list[str] = Field(default_factory=list)
    quality_score_mean: float = 0.0
    quality_score_min: float = 0.0
    quality_score_max: float = 0.0
    confidence_level_mean: float = 0.0
    confidence_level_min: float = 0.0
    confidence_level_max: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixBenchmarkBundle(BaseModel):
    benchmark_id: str = Field(default_factory=lambda: f"campaign_matrix_benchmark_{uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    output_dir: str = Field(default_factory=lambda: str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR))
    report_path: str | None = None
    baseline_campaign: DeliberationCampaignReport
    candidate_specs: list[DeliberationCampaignMatrixCandidateSpec] = Field(default_factory=list)
    entries: list[DeliberationCampaignMatrixComparisonEntry] = Field(default_factory=list)
    summary: DeliberationCampaignMatrixBenchmarkSummary
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixBenchmarkAuditEntry(BaseModel):
    rank: int
    candidate_index: int
    candidate_label: str
    candidate_campaign_id: str
    runtime: str
    engine: str
    comparison_id: str
    comparable: bool = False
    mismatch_reasons: list[str] = Field(default_factory=list)
    quality_score_mean: float = 0.0
    confidence_level_mean: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixBenchmarkAuditSummary(BaseModel):
    benchmark_id: str
    benchmark_report_path: str | None = None
    baseline_campaign_id: str
    baseline_runtime: str
    baseline_engine: str
    candidate_count: int
    comparable_count: int = 0
    mismatch_count: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    candidate_labels: list[str] = Field(default_factory=list)
    candidate_campaign_ids: list[str] = Field(default_factory=list)
    comparison_ids: list[str] = Field(default_factory=list)
    runtime_values: list[str] = Field(default_factory=list)
    engine_values: list[str] = Field(default_factory=list)
    quality_score_mean: float = 0.0
    quality_score_min: float = 0.0
    quality_score_max: float = 0.0
    confidence_level_mean: float = 0.0
    confidence_level_min: float = 0.0
    confidence_level_max: float = 0.0
    best_candidate_rank: int = 0
    best_candidate_label: str = ""
    best_candidate_campaign_id: str = ""
    best_candidate_quality_score_mean: float = 0.0
    best_candidate_confidence_level_mean: float = 0.0
    worst_candidate_rank: int = 0
    worst_candidate_label: str = ""
    worst_candidate_campaign_id: str = ""
    worst_candidate_quality_score_mean: float = 0.0
    worst_candidate_confidence_level_mean: float = 0.0
    mismatch_reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixBenchmarkAudit(BaseModel):
    benchmark_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    output_dir: str = Field(default_factory=lambda: str(DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR))
    benchmark_report_path: str | None = None
    entries: list[DeliberationCampaignMatrixBenchmarkAuditEntry] = Field(default_factory=list)
    summary: DeliberationCampaignMatrixBenchmarkAuditSummary
    markdown: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixBenchmarkExport(BaseModel):
    export_id: str = Field(default_factory=lambda: f"campaign_matrix_benchmark_export_{uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    output_dir: str
    manifest_path: str | None = None
    content_path: str | None = None
    benchmark_id: str
    benchmark_report_path: str | None = None
    format: str = "markdown"
    candidate_count: int
    candidate_labels: list[str] = Field(default_factory=list)
    candidate_campaign_ids: list[str] = Field(default_factory=list)
    comparison_ids: list[str] = Field(default_factory=list)
    comparable: bool = True
    comparable_count: int = 0
    mismatch_count: int = 0
    mismatch_reasons: list[str] = Field(default_factory=list)
    quality_score_mean: float | None = None
    confidence_level_mean: float | None = None
    best_candidate_label: str = ""
    worst_candidate_label: str = ""
    best_candidate: dict[str, Any] | None = None
    worst_candidate: dict[str, Any] | None = None
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixBenchmarkExportComparisonEntry(BaseModel):
    export_id: str
    created_at: datetime
    benchmark_id: str
    benchmark_report_path: str | None = None
    format: str = "markdown"
    baseline_campaign_id: str = ""
    baseline_runtime: str = ""
    baseline_engine: str = ""
    candidate_count: int = 0
    candidate_labels: list[str] = Field(default_factory=list)
    candidate_campaign_ids: list[str] = Field(default_factory=list)
    comparison_ids: list[str] = Field(default_factory=list)
    candidate_structure_key: str = ""
    comparable: bool = True
    comparable_count: int = 0
    mismatch_count: int = 0
    mismatch_reasons: list[str] = Field(default_factory=list)
    quality_score_mean: float = 0.0
    confidence_level_mean: float = 0.0
    best_candidate_label: str = ""
    worst_candidate_label: str = ""
    manifest_path: str | None = None
    content_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixBenchmarkExportComparisonSummary(BaseModel):
    export_count: int
    export_ids: list[str] = Field(default_factory=list)
    benchmark_ids: list[str] = Field(default_factory=list)
    format_values: list[str] = Field(default_factory=list)
    baseline_runtime_values: list[str] = Field(default_factory=list)
    baseline_engine_values: list[str] = Field(default_factory=list)
    candidate_count_values: list[int] = Field(default_factory=list)
    candidate_structure_key_values: list[str] = Field(default_factory=list)
    comparable: bool = True
    mismatch_reasons: list[str] = Field(default_factory=list)
    comparable_export_count: int = 0
    mismatch_export_count: int = 0
    candidate_count_total: int = 0
    comparable_candidate_total: int = 0
    mismatch_candidate_total: int = 0
    quality_score_mean: float = 0.0
    quality_score_min: float = 0.0
    quality_score_max: float = 0.0
    confidence_level_mean: float = 0.0
    confidence_level_min: float = 0.0
    confidence_level_max: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixBenchmarkExportComparisonReport(BaseModel):
    comparison_id: str = Field(default_factory=lambda: f"campaign_matrix_export_compare_{uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    output_dir: str
    report_path: str | None = None
    requested_export_ids: list[str] = Field(default_factory=list)
    latest: int | None = None
    entries: list[DeliberationCampaignMatrixBenchmarkExportComparisonEntry] = Field(default_factory=list)
    summary: DeliberationCampaignMatrixBenchmarkExportComparisonSummary
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixBenchmarkExportComparisonAudit(BaseModel):
    comparison_id: str
    created_at: datetime
    output_dir: str
    report_path: str | None = None
    requested_export_ids: list[str] = Field(default_factory=list)
    latest: int | None = None
    export_count: int
    export_ids: list[str] = Field(default_factory=list)
    comparable: bool = True
    mismatch_reasons: list[str] = Field(default_factory=list)
    entries: list[DeliberationCampaignMatrixBenchmarkExportComparisonEntry] = Field(default_factory=list)
    summary: DeliberationCampaignMatrixBenchmarkExportComparisonSummary
    markdown: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixBenchmarkExportComparisonExport(BaseModel):
    export_id: str = Field(default_factory=lambda: f"campaign_matrix_export_compare_export_{uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    output_dir: str
    manifest_path: str | None = None
    content_path: str | None = None
    comparison_id: str
    comparison_report_path: str | None = None
    format: str = "markdown"
    export_count: int
    export_ids: list[str] = Field(default_factory=list)
    comparable: bool = True
    mismatch_reasons: list[str] = Field(default_factory=list)
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixBenchmarkExportComparisonBundle(BaseModel):
    comparison_report: DeliberationCampaignMatrixBenchmarkExportComparisonReport
    audit: DeliberationCampaignMatrixBenchmarkExportComparisonAudit
    export: DeliberationCampaignMatrixBenchmarkExportComparisonExport
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixBenchmarkComparisonEntry(BaseModel):
    benchmark_id: str
    created_at: datetime
    baseline_campaign_id: str
    topic: str
    mode: str
    baseline_runtime: str
    baseline_engine: str
    sample_count_requested: int
    stability_runs: int
    candidate_count: int
    candidate_labels: list[str] = Field(default_factory=list)
    candidate_runtimes: list[str] = Field(default_factory=list)
    candidate_engines: list[str] = Field(default_factory=list)
    candidate_structure_key: str = ""
    comparison_ids: list[str] = Field(default_factory=list)
    comparable_count: int = 0
    mismatch_count: int = 0
    quality_score_mean: float = 0.0
    quality_score_min: float = 0.0
    quality_score_max: float = 0.0
    confidence_level_mean: float = 0.0
    confidence_level_min: float = 0.0
    confidence_level_max: float = 0.0
    report_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixBenchmarkComparisonSummary(BaseModel):
    benchmark_count: int
    benchmark_ids: list[str] = Field(default_factory=list)
    status_counts: dict[str, int] = Field(default_factory=dict)
    topic_values: list[str] = Field(default_factory=list)
    mode_values: list[str] = Field(default_factory=list)
    baseline_runtime_values: list[str] = Field(default_factory=list)
    baseline_engine_values: list[str] = Field(default_factory=list)
    runtime_values: list[str] = Field(default_factory=list)
    engine_values: list[str] = Field(default_factory=list)
    sample_count_values: list[int] = Field(default_factory=list)
    stability_runs_values: list[int] = Field(default_factory=list)
    candidate_count_values: list[int] = Field(default_factory=list)
    candidate_structure_key_values: list[str] = Field(default_factory=list)
    comparable: bool = True
    mismatch_reasons: list[str] = Field(default_factory=list)
    quality_score_mean: float = 0.0
    quality_score_min: float = 0.0
    quality_score_max: float = 0.0
    confidence_level_mean: float = 0.0
    confidence_level_min: float = 0.0
    confidence_level_max: float = 0.0
    candidate_count_total: int = 0
    comparable_count_total: int = 0
    mismatch_count_total: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixBenchmarkComparisonReport(BaseModel):
    comparison_id: str = Field(default_factory=lambda: f"campaign_matrix_compare_{uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    output_dir: str
    report_path: str | None = None
    requested_benchmark_ids: list[str] = Field(default_factory=list)
    latest: int | None = None
    entries: list[DeliberationCampaignMatrixBenchmarkComparisonEntry] = Field(default_factory=list)
    summary: DeliberationCampaignMatrixBenchmarkComparisonSummary
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixBenchmarkComparisonAudit(BaseModel):
    comparison_id: str
    created_at: datetime
    output_dir: str
    report_path: str | None = None
    requested_benchmark_ids: list[str] = Field(default_factory=list)
    latest: int | None = None
    benchmark_count: int
    benchmark_ids: list[str] = Field(default_factory=list)
    comparable: bool = True
    mismatch_reasons: list[str] = Field(default_factory=list)
    entries: list[DeliberationCampaignMatrixBenchmarkComparisonEntry] = Field(default_factory=list)
    summary: DeliberationCampaignMatrixBenchmarkComparisonSummary
    markdown: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixBenchmarkComparisonExport(BaseModel):
    export_id: str = Field(default_factory=lambda: f"campaign_matrix_compare_export_{uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    output_dir: str
    manifest_path: str | None = None
    content_path: str | None = None
    comparison_id: str
    comparison_report_path: str | None = None
    format: str = "markdown"
    benchmark_count: int
    benchmark_ids: list[str] = Field(default_factory=list)
    comparable: bool = True
    mismatch_reasons: list[str] = Field(default_factory=list)
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignMatrixBenchmarkComparisonBundle(BaseModel):
    comparison_report: DeliberationCampaignMatrixBenchmarkComparisonReport
    audit: DeliberationCampaignMatrixBenchmarkComparisonAudit
    export: DeliberationCampaignMatrixBenchmarkComparisonExport
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignArtifactIndex(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    output_dirs: dict[str, str] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    campaigns: list[dict[str, Any]] = Field(default_factory=list)
    comparisons: list[dict[str, Any]] = Field(default_factory=list)
    exports: list[dict[str, Any]] = Field(default_factory=list)
    benchmarks: list[dict[str, Any]] = Field(default_factory=list)
    matrix_benchmarks: list[dict[str, Any]] = Field(default_factory=list)
    matrix_benchmark_exports: list[dict[str, Any]] = Field(default_factory=list)
    matrix_benchmark_export_comparisons: list[dict[str, Any]] = Field(default_factory=list)
    matrix_benchmark_export_comparison_exports: list[dict[str, Any]] = Field(default_factory=list)
    matrix_benchmark_comparisons: list[dict[str, Any]] = Field(default_factory=list)
    matrix_benchmark_comparison_exports: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignDashboardRow(BaseModel):
    artifact_kind: str
    artifact_id: str
    created_at: datetime
    status: str | None = None
    comparable: bool | None = None
    quality_score_mean: float | None = None
    confidence_level_mean: float | None = None
    runtime_summary: str = ""
    engine_summary: str = ""
    artifact_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignDashboard(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    kinds: list[str] = Field(default_factory=list)
    limit: int | None = None
    sort_by: str = "created_at"
    campaign_status: DeliberationCampaignStatus | str | None = None
    comparable_only: bool = False
    rows: list[DeliberationCampaignDashboardRow] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCampaignReport(BaseModel):
    campaign_id: str
    status: DeliberationCampaignStatus
    topic: str
    objective: str
    mode: DeliberationMode
    runtime_requested: str
    engine_requested: str
    ensemble_engines: list[str] = Field(default_factory=list)
    max_agents: int = 6
    population_size: int | None = None
    rounds: int = 2
    time_horizon: str = "7d"
    sample_count_requested: int
    stability_runs: int
    allow_fallback_requested: bool
    allow_fallback_effective: bool
    fallback_guard_applied: bool
    fallback_guard_reason: str | None = None
    config_path: str = "config.yaml"
    benchmark_path: str | None = None
    backend_mode: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    output_dir: str
    report_path: str | None = None
    samples: list[DeliberationCampaignSample] = Field(default_factory=list)
    summary: DeliberationCampaignSummary
    metadata: dict[str, Any] = Field(default_factory=dict)


def run_deliberation_campaign_sync(
    *,
    topic: str,
    objective: str | None = None,
    mode: DeliberationMode | str = DeliberationMode.committee,
    participants: list[str] | None = None,
    documents: list[str] | None = None,
    entities: list[Any] | None = None,
    interventions: list[str] | None = None,
    max_agents: int = 6,
    population_size: int | None = None,
    rounds: int = 2,
    time_horizon: str = "7d",
    sample_count: int = 3,
    stability_runs: int = 1,
    runtime: str = "pydanticai",
    allow_fallback: bool = True,
    engine_preference: EnginePreference | str = EnginePreference.agentsociety,
    ensemble_engines: list[EnginePreference | str] | None = None,
    budget_max: float = 10.0,
    timeout_seconds: int = 1800,
    benchmark_path: str | None = None,
    config_path: str = "config.yaml",
    backend_mode: str | None = None,
    persist: bool = True,
    output_dir: str | Path | None = None,
    client: Any | None = None,
    campaign_id: str | None = None,
    runner: Callable[..., DeliberationResult] | None = None,
) -> DeliberationCampaignReport:
    sample_count = max(1, int(sample_count))
    stability_runs = max(1, int(stability_runs))
    requested_allow_fallback = bool(allow_fallback)
    fallback_guard_applied = (sample_count > 1 or stability_runs > 1) and requested_allow_fallback
    effective_allow_fallback = False if fallback_guard_applied else requested_allow_fallback
    fallback_guard_reason = (
        "fallback_disabled_for_repeated_campaign_comparison" if fallback_guard_applied else None
    )
    selected_mode = _normalize_mode(mode)
    selected_engine = _normalize_engine(engine_preference)
    selected_ensemble_engines = [_normalize_engine(engine) for engine in (ensemble_engines or [])]
    runner_fn = runner or run_deliberation_sync
    campaign_id = _normalize_text(campaign_id) or f"campaign_{uuid4().hex[:12]}"
    campaign_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR) / campaign_id
    samples_dir = campaign_dir / "samples"
    sample_summaries: list[DeliberationCampaignSample] = []
    quality_scores: list[float] = []
    confidence_levels: list[float] = []

    for index in range(1, sample_count + 1):
        sample_id = f"sample_{index:02d}"
        sample_dir = samples_dir / sample_id
        sample_output_dir = sample_dir if persist else None
        try:
            result = runner_fn(
                topic=topic,
                objective=objective,
                mode=selected_mode,
                participants=participants,
                documents=documents,
                entities=entities,
                interventions=interventions,
                max_agents=max_agents,
                population_size=population_size,
                rounds=rounds,
                time_horizon=time_horizon,
                runtime=runtime,
                allow_fallback=effective_allow_fallback,
                engine_preference=engine_preference,
                ensemble_engines=ensemble_engines,
                budget_max=budget_max,
                timeout_seconds=timeout_seconds,
                benchmark_path=benchmark_path,
                config_path=config_path,
                backend_mode=backend_mode,
                stability_runs=stability_runs,
                persist=persist,
                output_dir=sample_output_dir,
                client=client,
            )
            sample_summary = _sample_summary_from_result(
                result,
                sample_id=sample_id,
                sample_index=index,
                result_path=_persist_sample_result(result, sample_dir) if persist else None,
                campaign_id=campaign_id,
                sample_count=sample_count,
                stability_runs=stability_runs,
                requested_allow_fallback=requested_allow_fallback,
                effective_allow_fallback=effective_allow_fallback,
                fallback_guard_applied=fallback_guard_applied,
                fallback_guard_reason=fallback_guard_reason,
            )
            sample_summaries.append(sample_summary)
            if sample_summary.status != DeliberationCampaignStatus.failed.value:
                quality_scores.append(sample_summary.quality_score)
                confidence_levels.append(sample_summary.confidence_level)
        except Exception as exc:
            sample_summaries.append(
                DeliberationCampaignSample(
                    sample_id=sample_id,
                    sample_index=index,
                    deliberation_id="",
                    status=DeliberationCampaignStatus.failed.value,
                    topic=topic,
                    objective=objective or "",
                    runtime_requested=_normalize_text(runtime),
                    runtime_used=None,
                    fallback_used=False,
                    engine_requested=_normalize_text(engine_preference),
                    engine_used=None,
                    comparability={
                        "campaign_id": campaign_id,
                        "sample_id": sample_id,
                        "sample_index": index,
                        "sample_count_requested": sample_count,
                        "stability_runs": stability_runs,
                        "allow_fallback_requested": requested_allow_fallback,
                        "allow_fallback_effective": effective_allow_fallback,
                        "campaign_fallback_guard_applied": fallback_guard_applied,
                        "campaign_fallback_guard_reason": fallback_guard_reason,
                    },
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
            )

    status_counts = Counter(sample.status for sample in sample_summaries)
    runtime_counts = Counter(
        _normalize_text(sample.runtime_used or sample.runtime_requested or "unknown") for sample in sample_summaries
    )
    engine_counts = Counter(_normalize_text(sample.engine_used or sample.engine_requested or "unknown") for sample in sample_summaries)
    fallback_count = sum(1 for sample in sample_summaries if sample.fallback_used)
    successful_samples = [sample for sample in sample_summaries if sample.status != DeliberationCampaignStatus.failed.value]
    sample_ids = [sample.sample_id for sample in sample_summaries]
    deliberation_ids = [sample.deliberation_id for sample in successful_samples if sample.deliberation_id]
    aggregate_metadata = {
        "campaign_id": campaign_id,
        "sample_count_requested": sample_count,
        "sample_count_completed": len(successful_samples),
        "allow_fallback_requested": requested_allow_fallback,
        "allow_fallback_effective": effective_allow_fallback,
        "fallback_guard_applied": fallback_guard_applied,
        "fallback_guard_reason": fallback_guard_reason,
        "campaign_fallback_guard_applied": fallback_guard_applied,
        "campaign_fallback_guard_reason": fallback_guard_reason,
        "runtime_requested": _normalize_text(runtime),
        "engine_requested": _normalize_text(engine_preference),
        "ensemble_engines": [_normalize_text(engine) for engine in selected_ensemble_engines],
        "max_agents": max_agents,
        "population_size": population_size,
        "rounds": rounds,
        "time_horizon": _normalize_text(time_horizon),
        "sample_ids": sample_ids,
        "deliberation_ids": deliberation_ids,
    }
    campaign_stability_summary = None
    if quality_scores:
        campaign_stability_summary = DeliberationStabilitySummary.from_scores(
            quality_scores,
            minimum_sample_count=1 if sample_count == 1 else 2,
            metric_name="campaign_quality_score",
            comparison_key=_campaign_comparison_key(
                topic=topic,
                objective=objective or "",
                mode=selected_mode,
                runtime=runtime,
                engine_preference=selected_engine,
                sample_count=sample_count,
                stability_runs=stability_runs,
            ),
            sample_run_ids=deliberation_ids or sample_ids,
            metadata=aggregate_metadata,
        )
    summary = DeliberationCampaignSummary(
        sample_count_requested=sample_count,
        sample_count_completed=len(successful_samples),
        sample_count_failed=len(sample_summaries) - len(successful_samples),
        sample_ids=sample_ids,
        deliberation_ids=deliberation_ids,
        quality_scores=quality_scores,
        confidence_levels=confidence_levels,
        runtime_counts=dict(runtime_counts),
        engine_counts=dict(engine_counts),
        status_counts=dict(status_counts),
        fallback_count=fallback_count,
        quality_score_mean=mean(quality_scores) if quality_scores else 0.0,
        quality_score_min=min(quality_scores) if quality_scores else 0.0,
        quality_score_max=max(quality_scores) if quality_scores else 0.0,
        confidence_level_mean=mean(confidence_levels) if confidence_levels else 0.0,
        confidence_level_min=min(confidence_levels) if confidence_levels else 0.0,
        confidence_level_max=max(confidence_levels) if confidence_levels else 0.0,
        campaign_stability_summary=campaign_stability_summary,
        metadata=aggregate_metadata,
    )
    report_status = _campaign_status_from_samples(sample_summaries)
    report = DeliberationCampaignReport(
        campaign_id=campaign_id,
        status=report_status,
        topic=topic,
        objective=objective or f"Define the best strategy for: {topic}",
        mode=selected_mode,
        runtime_requested=_normalize_text(runtime),
        engine_requested=selected_engine.value,
        ensemble_engines=[engine.value for engine in selected_ensemble_engines],
        max_agents=max_agents,
        population_size=population_size,
        rounds=rounds,
        time_horizon=_normalize_text(time_horizon) or "7d",
        sample_count_requested=sample_count,
        stability_runs=stability_runs,
        allow_fallback_requested=requested_allow_fallback,
        allow_fallback_effective=effective_allow_fallback,
        fallback_guard_applied=fallback_guard_applied,
        fallback_guard_reason=fallback_guard_reason,
        config_path=config_path,
        benchmark_path=benchmark_path,
        backend_mode=backend_mode,
        output_dir=str(campaign_dir),
        samples=sample_summaries,
        summary=summary,
        metadata={
            **aggregate_metadata,
            "campaign_status": report_status.value,
            "persisted": persist,
        },
    )

    if persist:
        campaign_dir.mkdir(parents=True, exist_ok=True)
        report_path = campaign_dir / "report.json"
        report.report_path = str(report_path)
        report.metadata["report_path"] = str(report_path)
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    return report


def load_deliberation_campaign_report(
    campaign_id: str,
    *,
    output_dir: str | Path | None = None,
) -> DeliberationCampaignReport:
    report_path = _campaign_report_path(campaign_id, output_dir=output_dir)
    return DeliberationCampaignReport.model_validate_json(report_path.read_text(encoding="utf-8"))


def compare_deliberation_campaign_reports(
    *,
    campaign_ids: list[str] | None = None,
    latest: int | None = None,
    output_dir: str | Path | None = None,
    persist: bool = False,
    comparison_output_dir: str | Path | None = None,
) -> DeliberationCampaignComparisonReport:
    selected_reports = _selected_deliberation_campaign_reports(
        campaign_ids=campaign_ids,
        latest=latest,
        output_dir=output_dir,
    )
    if len(selected_reports) < 2:
        raise ValueError("At least two campaign reports are required for comparison.")
    entries = [_comparison_entry_from_report(report) for report in selected_reports]
    summary = _comparison_summary_from_entries(entries, selected_reports)
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR)
    comparison_base_dir = Path(
        comparison_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR
    )
    requested_campaign_ids = [_normalize_text(campaign_id) for campaign_id in (campaign_ids or []) if _normalize_text(campaign_id)]
    report = DeliberationCampaignComparisonReport(
        output_dir=str(base_dir),
        requested_campaign_ids=requested_campaign_ids,
        latest=latest,
        entries=entries,
        summary=summary,
        metadata={
            "output_dir": str(base_dir),
            "requested_campaign_ids": requested_campaign_ids,
            "latest": latest,
            "selected_campaign_ids": [entry.campaign_id for entry in entries],
            "comparison_key": summary.comparison_key_values[0] if len(summary.comparison_key_values) == 1 else None,
        },
    )
    if persist:
        comparison_base_dir.mkdir(parents=True, exist_ok=True)
        comparison_path = comparison_base_dir / report.comparison_id / "report.json"
        comparison_path.parent.mkdir(parents=True, exist_ok=True)
        report.report_path = str(comparison_path)
        report.metadata["report_path"] = str(comparison_path)
        report.metadata["persisted"] = True
        comparison_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report


def load_deliberation_campaign_comparison_report(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
) -> DeliberationCampaignComparisonReport:
    report_path = _comparison_report_path(comparison_id, output_dir=output_dir)
    return DeliberationCampaignComparisonReport.model_validate_json(report_path.read_text(encoding="utf-8"))


def list_deliberation_campaign_comparison_reports(
    *,
    output_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[DeliberationCampaignComparisonReport]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR)
    if not base_dir.exists():
        return []

    reports: list[DeliberationCampaignComparisonReport] = []
    for comparison_dir in base_dir.iterdir():
        if not comparison_dir.is_dir():
            continue
        report_path = comparison_dir / "report.json"
        if not report_path.is_file():
            continue
        try:
            report = DeliberationCampaignComparisonReport.model_validate_json(
                report_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, json.JSONDecodeError):
            continue
        reports.append(report)

    reports.sort(
        key=lambda report: (
            _campaign_created_at_sort_key(report.created_at),
            report.comparison_id,
        ),
        reverse=True,
    )
    if limit is None:
        return reports
    return reports[: max(0, int(limit))]


def build_deliberation_campaign_comparison_audit(
    comparison_report: DeliberationCampaignComparisonReport | dict[str, Any],
    *,
    include_markdown: bool = True,
) -> DeliberationCampaignComparisonAudit:
    report = (
        comparison_report
        if isinstance(comparison_report, DeliberationCampaignComparisonReport)
        else DeliberationCampaignComparisonReport.model_validate(comparison_report)
    )
    summary = report.summary
    audit = DeliberationCampaignComparisonAudit(
        comparison_id=report.comparison_id,
        created_at=report.created_at,
        output_dir=report.output_dir,
        report_path=report.report_path,
        requested_campaign_ids=list(report.requested_campaign_ids),
        latest=report.latest,
        campaign_count=summary.campaign_count,
        campaign_ids=list(summary.campaign_ids),
        comparable=summary.comparable,
        mismatch_reasons=list(summary.mismatch_reasons),
        entries=list(report.entries),
        summary=summary,
        metadata={
            **report.metadata,
            "report_path": report.report_path,
            "comparison_key": summary.comparison_key_values[0] if len(summary.comparison_key_values) == 1 else None,
            "entry_count": len(report.entries),
        },
    )
    if include_markdown:
        audit.markdown = render_deliberation_campaign_comparison_markdown(audit)
    return audit


def load_deliberation_campaign_comparison_audit(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
    include_markdown: bool = True,
) -> DeliberationCampaignComparisonAudit:
    report = load_deliberation_campaign_comparison_report(comparison_id, output_dir=output_dir)
    return build_deliberation_campaign_comparison_audit(report, include_markdown=include_markdown)


def compare_deliberation_campaign_bundle(
    *,
    campaign_ids: list[str] | None = None,
    latest: int | None = None,
    output_dir: str | Path | None = None,
    persist: bool = True,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
    format: str = "markdown",
    export_id: str | None = None,
) -> DeliberationCampaignComparisonBundle:
    normalized_format = str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        raise ValueError("format must be one of: markdown, json")

    comparison_report = compare_deliberation_campaign_reports(
        campaign_ids=campaign_ids,
        latest=latest,
        output_dir=output_dir,
        persist=persist,
        comparison_output_dir=comparison_output_dir,
    )
    audit = build_deliberation_campaign_comparison_audit(
        comparison_report,
        include_markdown=normalized_format == "markdown",
    )
    export = materialize_deliberation_campaign_comparison_export(
        audit,
        format=normalized_format,
        output_dir=export_output_dir,
        export_id=_normalize_text(export_id) or f"{comparison_report.comparison_id}__{normalized_format}",
    )
    return DeliberationCampaignComparisonBundle(
        comparison_report=comparison_report,
        audit=audit,
        export=export,
        metadata={
            "campaign_ids": list(campaign_ids or []),
            "latest": latest,
            "persisted": persist,
            "comparison_output_dir": str(
                Path(comparison_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR)
            ),
            "export_output_dir": str(Path(export_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR)),
            "format": normalized_format,
            "comparison_id": comparison_report.comparison_id,
            "export_id": export.export_id,
        },
    )


def run_deliberation_campaign_benchmark_sync(
    *,
    topic: str,
    objective: str | None = None,
    mode: DeliberationMode | str = DeliberationMode.committee,
    participants: list[str] | None = None,
    documents: list[str] | None = None,
    entities: list[Any] | None = None,
    interventions: list[str] | None = None,
    max_agents: int = 6,
    population_size: int | None = None,
    rounds: int = 2,
    time_horizon: str = "7d",
    sample_count: int = 3,
    stability_runs: int = 1,
    baseline_runtime: str = "pydanticai",
    candidate_runtime: str = "legacy",
    allow_fallback: bool = True,
    baseline_engine_preference: EnginePreference | str = EnginePreference.agentsociety,
    candidate_engine_preference: EnginePreference | str = EnginePreference.oasis,
    ensemble_engines: list[EnginePreference | str] | None = None,
    budget_max: float = 10.0,
    timeout_seconds: int = 1800,
    benchmark_path: str | None = None,
    config_path: str = "config.yaml",
    backend_mode: str | None = None,
    persist: bool = True,
    output_dir: str | Path | None = None,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
    benchmark_output_dir: str | Path | None = None,
    format: str = "markdown",
    baseline_campaign_id: str | None = None,
    candidate_campaign_id: str | None = None,
    client: Any | None = None,
    runner: Callable[..., DeliberationResult] | None = None,
) -> DeliberationCampaignBenchmarkBundle:
    if not persist:
        raise ValueError("run_deliberation_campaign_benchmark_sync requires persist=True")
    selected_mode = _normalize_mode(mode)
    selected_baseline_engine = _normalize_engine(baseline_engine_preference)
    selected_candidate_engine = _normalize_engine(candidate_engine_preference)
    normalized_format = str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        raise ValueError("format must be one of: markdown, json")

    shared_output_dir = output_dir or DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR
    baseline_campaign_id = _normalize_text(baseline_campaign_id) or f"benchmark_baseline_{uuid4().hex[:12]}"
    candidate_campaign_id = _normalize_text(candidate_campaign_id) or f"benchmark_candidate_{uuid4().hex[:12]}"

    baseline_campaign = run_deliberation_campaign_sync(
        topic=topic,
        objective=objective,
        mode=selected_mode,
        participants=participants,
        documents=documents,
        entities=entities,
        interventions=interventions,
        max_agents=max_agents,
        population_size=population_size,
        rounds=rounds,
        time_horizon=time_horizon,
        sample_count=sample_count,
        stability_runs=stability_runs,
        runtime=baseline_runtime,
        allow_fallback=allow_fallback,
        engine_preference=selected_baseline_engine,
        ensemble_engines=ensemble_engines,
        budget_max=budget_max,
        timeout_seconds=timeout_seconds,
        benchmark_path=benchmark_path,
        config_path=config_path,
        backend_mode=backend_mode,
        persist=persist,
        output_dir=shared_output_dir,
        client=client,
        campaign_id=baseline_campaign_id,
        runner=runner,
    )
    candidate_campaign = run_deliberation_campaign_sync(
        topic=topic,
        objective=objective,
        mode=selected_mode,
        participants=participants,
        documents=documents,
        entities=entities,
        interventions=interventions,
        max_agents=max_agents,
        population_size=population_size,
        rounds=rounds,
        time_horizon=time_horizon,
        sample_count=sample_count,
        stability_runs=stability_runs,
        runtime=candidate_runtime,
        allow_fallback=allow_fallback,
        engine_preference=selected_candidate_engine,
        ensemble_engines=ensemble_engines,
        budget_max=budget_max,
        timeout_seconds=timeout_seconds,
        benchmark_path=benchmark_path,
        config_path=config_path,
        backend_mode=backend_mode,
        persist=persist,
        output_dir=shared_output_dir,
        client=client,
        campaign_id=candidate_campaign_id,
        runner=runner,
    )

    comparison_bundle_result = compare_deliberation_campaign_bundle(
        campaign_ids=[baseline_campaign.campaign_id, candidate_campaign.campaign_id],
        output_dir=shared_output_dir,
        persist=True,
        comparison_output_dir=comparison_output_dir,
        export_output_dir=export_output_dir,
        format=normalized_format,
    )
    comparison_bundle_payload = (
        comparison_bundle_result.model_dump(mode="json")
        if hasattr(comparison_bundle_result, "model_dump")
        else dict(comparison_bundle_result)
    )
    comparison_bundle = (
        comparison_bundle_result
        if isinstance(comparison_bundle_result, DeliberationCampaignComparisonBundle)
        else DeliberationCampaignComparisonBundle.model_validate(comparison_bundle_payload)
    )

    benchmark_id = (
        f"{baseline_campaign_id}__vs__{candidate_campaign_id}"
        if baseline_campaign_id and candidate_campaign_id
        else f"campaign_benchmark_{uuid4().hex[:12]}"
    )
    benchmark_base_dir = Path(benchmark_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR)
    benchmark_created_at = datetime.now(timezone.utc)
    benchmark_bundle = DeliberationCampaignBenchmarkBundle(
        benchmark_id=benchmark_id,
        created_at=benchmark_created_at,
        output_dir=str(benchmark_base_dir),
        report_path=None,
        baseline_campaign=baseline_campaign,
        candidate_campaign=candidate_campaign,
        comparison_bundle=comparison_bundle,
        metadata={
            "benchmark_id": benchmark_id,
            "created_at": benchmark_created_at.isoformat(),
            "campaign_ids": [baseline_campaign.campaign_id, candidate_campaign.campaign_id],
            "baseline_campaign_id": baseline_campaign.campaign_id,
            "candidate_campaign_id": candidate_campaign.campaign_id,
            "baseline_runtime": _normalize_text(baseline_runtime),
            "candidate_runtime": _normalize_text(candidate_runtime),
            "baseline_engine_preference": selected_baseline_engine.value,
            "candidate_engine_preference": selected_candidate_engine.value,
            "sample_count": sample_count,
            "stability_runs": stability_runs,
            "comparison_id": comparison_bundle.comparison_report.comparison_id,
            "export_id": comparison_bundle.export.export_id,
            "comparison_output_dir": str(
                Path(comparison_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR)
            ),
            "export_output_dir": str(Path(export_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR)),
            "benchmark_output_dir": str(benchmark_base_dir),
            "output_dir": str(Path(shared_output_dir)),
            "format": normalized_format,
            "persisted": persist,
        },
    )

    benchmark_report_path = _benchmark_report_path(benchmark_bundle.benchmark_id, output_dir=benchmark_base_dir)
    benchmark_report_path.parent.mkdir(parents=True, exist_ok=True)
    benchmark_bundle.report_path = str(benchmark_report_path)
    benchmark_bundle.metadata["report_path"] = str(benchmark_report_path)
    benchmark_bundle.metadata["created_at"] = benchmark_bundle.created_at.isoformat()
    benchmark_report_path.write_text(benchmark_bundle.model_dump_json(indent=2), encoding="utf-8")
    return benchmark_bundle


def run_deliberation_campaign_matrix_benchmark_sync(
    *,
    topic: str,
    objective: str | None = None,
    mode: DeliberationMode | str = DeliberationMode.committee,
    participants: list[str] | None = None,
    documents: list[str] | None = None,
    entities: list[Any] | None = None,
    interventions: list[str] | None = None,
    max_agents: int = 6,
    population_size: int | None = None,
    rounds: int = 2,
    time_horizon: str = "7d",
    sample_count: int = 3,
    stability_runs: int = 1,
    baseline_runtime: str = "pydanticai",
    baseline_engine_preference: EnginePreference | str = EnginePreference.agentsociety,
    candidate_specs: list[DeliberationCampaignMatrixCandidateSpec | dict[str, Any]] | None = None,
    allow_fallback: bool = True,
    ensemble_engines: list[EnginePreference | str] | None = None,
    budget_max: float = 10.0,
    timeout_seconds: int = 1800,
    benchmark_path: str | None = None,
    config_path: str = "config.yaml",
    backend_mode: str | None = None,
    persist: bool = True,
    output_dir: str | Path | None = None,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
    benchmark_output_dir: str | Path | None = None,
    format: str = "markdown",
    benchmark_id: str | None = None,
    baseline_campaign_id: str | None = None,
    client: Any | None = None,
    runner: Callable[..., DeliberationResult] | None = None,
) -> DeliberationCampaignMatrixBenchmarkBundle:
    if not persist:
        raise ValueError("run_deliberation_campaign_matrix_benchmark_sync requires persist=True")

    normalized_format = str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        raise ValueError("format must be one of: markdown, json")

    selected_mode = _normalize_mode(mode)
    selected_baseline_engine = _normalize_engine(baseline_engine_preference)
    normalized_candidate_specs = [
        DeliberationCampaignMatrixCandidateSpec.model_validate(candidate_spec)
        for candidate_spec in (candidate_specs or [])
    ]
    if not normalized_candidate_specs:
        raise ValueError("candidate_specs must contain at least one candidate")

    benchmark_id = _normalize_text(benchmark_id) or f"campaign_matrix_benchmark_{uuid4().hex[:12]}"
    shared_output_dir = output_dir or DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR
    baseline_campaign_id = _normalize_text(baseline_campaign_id) or f"{benchmark_id}__baseline"
    baseline_campaign = run_deliberation_campaign_sync(
        topic=topic,
        objective=objective,
        mode=selected_mode,
        participants=participants,
        documents=documents,
        entities=entities,
        interventions=interventions,
        max_agents=max_agents,
        population_size=population_size,
        rounds=rounds,
        time_horizon=time_horizon,
        sample_count=sample_count,
        stability_runs=stability_runs,
        runtime=baseline_runtime,
        allow_fallback=allow_fallback,
        engine_preference=selected_baseline_engine,
        ensemble_engines=ensemble_engines,
        budget_max=budget_max,
        timeout_seconds=timeout_seconds,
        benchmark_path=benchmark_path,
        config_path=config_path,
        backend_mode=backend_mode,
        persist=persist,
        output_dir=shared_output_dir,
        client=client,
        campaign_id=baseline_campaign_id,
        runner=runner,
    )

    entries: list[DeliberationCampaignMatrixComparisonEntry] = []
    quality_scores: list[float] = []
    confidence_levels: list[float] = []
    runtime_values = [_normalize_text(baseline_runtime)]
    engine_values = [selected_baseline_engine.value]
    candidate_campaign_ids: list[str] = []
    candidate_labels: list[str] = []
    comparison_ids: list[str] = []

    for index, candidate_spec in enumerate(normalized_candidate_specs, start=1):
        candidate_label = _normalize_text(candidate_spec.label) or f"candidate_{index:02d}"
        candidate_campaign_id = (
            _normalize_text(candidate_spec.campaign_id) or f"{benchmark_id}__candidate_{index:02d}"
        )
        candidate_campaign = run_deliberation_campaign_sync(
            topic=topic,
            objective=objective,
            mode=selected_mode,
            participants=participants,
            documents=documents,
            entities=entities,
            interventions=interventions,
            max_agents=max_agents,
            population_size=population_size,
            rounds=rounds,
            time_horizon=time_horizon,
            sample_count=sample_count,
            stability_runs=stability_runs,
            runtime=candidate_spec.runtime,
            allow_fallback=allow_fallback,
            engine_preference=candidate_spec.engine_preference,
            ensemble_engines=ensemble_engines,
            budget_max=budget_max,
            timeout_seconds=timeout_seconds,
            benchmark_path=benchmark_path,
            config_path=config_path,
            backend_mode=backend_mode,
            persist=persist,
            output_dir=shared_output_dir,
            client=client,
            campaign_id=candidate_campaign_id,
            runner=runner,
        )
        comparison_bundle_result = compare_deliberation_campaign_bundle(
            campaign_ids=[baseline_campaign.campaign_id, candidate_campaign.campaign_id],
            output_dir=shared_output_dir,
            persist=True,
            comparison_output_dir=comparison_output_dir,
            export_output_dir=export_output_dir,
            format=normalized_format,
        )
        comparison_bundle_payload = (
            comparison_bundle_result.model_dump(mode="json")
            if hasattr(comparison_bundle_result, "model_dump")
            else dict(comparison_bundle_result)
        )
        comparison_bundle = (
            comparison_bundle_result
            if isinstance(comparison_bundle_result, DeliberationCampaignComparisonBundle)
            else DeliberationCampaignComparisonBundle.model_validate(comparison_bundle_payload)
        )
        candidate_campaign_ids.append(candidate_campaign.campaign_id)
        candidate_labels.append(candidate_label)
        comparison_ids.append(comparison_bundle.comparison_report.comparison_id)
        runtime_values.append(_normalize_text(candidate_spec.runtime))
        engine_values.append(_normalize_engine(candidate_spec.engine_preference).value)
        comparison_summary = comparison_bundle.comparison_report.summary
        quality_scores.append(comparison_summary.quality_score_mean)
        confidence_levels.append(comparison_summary.confidence_level_mean)
        entries.append(
            DeliberationCampaignMatrixComparisonEntry(
                candidate_index=index,
                candidate_label=candidate_label,
                candidate_spec=candidate_spec,
                candidate_campaign=candidate_campaign,
                comparison_bundle=comparison_bundle,
                metadata={
                    "candidate_index": index,
                    "candidate_label": candidate_label,
                    "candidate_campaign_id": candidate_campaign.campaign_id,
                    "candidate_runtime": _normalize_text(candidate_spec.runtime),
                    "candidate_engine_preference": _normalize_engine(candidate_spec.engine_preference).value,
                    "comparison_id": comparison_bundle.comparison_report.comparison_id,
                },
            )
        )

    comparable_count = sum(
        1 for entry in entries if entry.comparison_bundle.comparison_report.summary.comparable
    )
    mismatch_count = len(entries) - comparable_count
    status_counts = Counter(
        "comparable" if entry.comparison_bundle.comparison_report.summary.comparable else "mismatch"
        for entry in entries
    )
    benchmark_summary = DeliberationCampaignMatrixBenchmarkSummary(
        candidate_count=len(entries),
        candidate_labels=candidate_labels,
        candidate_campaign_ids=candidate_campaign_ids,
        comparison_ids=comparison_ids,
        comparable_count=comparable_count,
        mismatch_count=mismatch_count,
        status_counts=dict(status_counts),
        runtime_values=_sorted_unique_values(runtime_values),
        engine_values=_sorted_unique_values(engine_values),
        quality_score_mean=mean(quality_scores) if quality_scores else 0.0,
        quality_score_min=min(quality_scores) if quality_scores else 0.0,
        quality_score_max=max(quality_scores) if quality_scores else 0.0,
        confidence_level_mean=mean(confidence_levels) if confidence_levels else 0.0,
        confidence_level_min=min(confidence_levels) if confidence_levels else 0.0,
        confidence_level_max=max(confidence_levels) if confidence_levels else 0.0,
        metadata={
            "benchmark_id": benchmark_id,
            "baseline_campaign_id": baseline_campaign.campaign_id,
            "candidate_campaign_ids": candidate_campaign_ids,
            "candidate_labels": candidate_labels,
            "comparison_ids": comparison_ids,
        },
    )

    benchmark_base_dir = Path(benchmark_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR)
    benchmark_created_at = datetime.now(timezone.utc)
    benchmark_bundle = DeliberationCampaignMatrixBenchmarkBundle(
        benchmark_id=benchmark_id,
        created_at=benchmark_created_at,
        output_dir=str(benchmark_base_dir),
        report_path=None,
        baseline_campaign=baseline_campaign,
        candidate_specs=normalized_candidate_specs,
        entries=entries,
        summary=benchmark_summary,
        metadata={
            "benchmark_id": benchmark_id,
            "created_at": benchmark_created_at.isoformat(),
            "campaign_ids": [baseline_campaign.campaign_id, *candidate_campaign_ids],
            "baseline_campaign_id": baseline_campaign.campaign_id,
            "baseline_runtime": _normalize_text(baseline_runtime),
            "baseline_engine_preference": selected_baseline_engine.value,
            "candidate_count": len(entries),
            "candidate_campaign_ids": candidate_campaign_ids,
            "candidate_labels": candidate_labels,
            "comparison_ids": comparison_ids,
            "comparison_output_dir": str(
                Path(comparison_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR)
            ),
            "export_output_dir": str(Path(export_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR)),
            "benchmark_output_dir": str(benchmark_base_dir),
            "output_dir": str(Path(shared_output_dir)),
            "format": normalized_format,
            "persisted": persist,
        },
    )

    benchmark_report_path = _matrix_benchmark_report_path(benchmark_bundle.benchmark_id, output_dir=benchmark_base_dir)
    benchmark_report_path.parent.mkdir(parents=True, exist_ok=True)
    benchmark_bundle.report_path = str(benchmark_report_path)
    benchmark_bundle.metadata["report_path"] = str(benchmark_report_path)
    benchmark_bundle.metadata["created_at"] = benchmark_bundle.created_at.isoformat()
    benchmark_report_path.write_text(benchmark_bundle.model_dump_json(indent=2), encoding="utf-8")
    return benchmark_bundle


def _benchmark_report_path(benchmark_id: str, *, output_dir: str | Path | None = None) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR)
    return base_dir / benchmark_id / "report.json"


def _matrix_benchmark_report_path(matrix_benchmark_id: str, *, output_dir: str | Path | None = None) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR)
    return base_dir / matrix_benchmark_id / "report.json"


def _matrix_benchmark_audit_export_dir(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR)
    return base_dir / export_id


def _matrix_benchmark_audit_export_manifest_path(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
) -> Path:
    return _matrix_benchmark_audit_export_dir(export_id, output_dir=output_dir) / "manifest.json"


def _matrix_benchmark_audit_export_content_path(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> Path:
    extension = ".md" if str(format).strip().lower() == "markdown" else ".json"
    return _matrix_benchmark_audit_export_dir(export_id, output_dir=output_dir) / f"content{extension}"


def _matrix_benchmark_comparison_report_path(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR)
    return base_dir / comparison_id / "report.json"


def load_deliberation_campaign_benchmark(
    benchmark_id: str,
    *,
    output_dir: str | Path | None = None,
) -> DeliberationCampaignBenchmarkBundle:
    report_path = _benchmark_report_path(benchmark_id, output_dir=output_dir)
    return DeliberationCampaignBenchmarkBundle.model_validate_json(report_path.read_text(encoding="utf-8"))


def load_deliberation_campaign_matrix_benchmark(
    matrix_benchmark_id: str,
    *,
    output_dir: str | Path | None = None,
) -> DeliberationCampaignMatrixBenchmarkBundle:
    report_path = _matrix_benchmark_report_path(matrix_benchmark_id, output_dir=output_dir)
    return DeliberationCampaignMatrixBenchmarkBundle.model_validate_json(report_path.read_text(encoding="utf-8"))


def list_deliberation_campaign_benchmarks(
    *,
    output_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[DeliberationCampaignBenchmarkBundle]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR)
    if not base_dir.exists():
        return []

    benchmarks: list[DeliberationCampaignBenchmarkBundle] = []
    for benchmark_dir in base_dir.iterdir():
        if not benchmark_dir.is_dir():
            continue
        report_path = benchmark_dir / "report.json"
        if not report_path.is_file():
            continue
        try:
            benchmark = DeliberationCampaignBenchmarkBundle.model_validate_json(
                report_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, json.JSONDecodeError):
            continue
        benchmarks.append(benchmark)

    benchmarks.sort(
        key=lambda benchmark: (
            _campaign_created_at_sort_key(benchmark.created_at),
            benchmark.benchmark_id,
        ),
        reverse=True,
    )
    if limit is None:
        return benchmarks
    return benchmarks[: max(0, int(limit))]


def list_deliberation_campaign_matrix_benchmarks(
    *,
    output_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[DeliberationCampaignMatrixBenchmarkBundle]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR)
    if not base_dir.exists():
        return []

    matrix_benchmarks: list[DeliberationCampaignMatrixBenchmarkBundle] = []
    for matrix_benchmark_dir in base_dir.iterdir():
        if not matrix_benchmark_dir.is_dir():
            continue
        report_path = matrix_benchmark_dir / "report.json"
        if not report_path.is_file():
            continue
        try:
            matrix_benchmark = DeliberationCampaignMatrixBenchmarkBundle.model_validate_json(
                report_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, json.JSONDecodeError):
            continue
        matrix_benchmarks.append(matrix_benchmark)

    matrix_benchmarks.sort(
        key=lambda matrix_benchmark: (
            _campaign_created_at_sort_key(matrix_benchmark.created_at),
            matrix_benchmark.benchmark_id,
        ),
        reverse=True,
    )
    if limit is None:
        return matrix_benchmarks
    return matrix_benchmarks[: max(0, int(limit))]


def _matrix_benchmark_audit_rank_key(
    entry: DeliberationCampaignMatrixComparisonEntry,
) -> tuple[Any, ...]:
    summary = entry.comparison_bundle.comparison_report.summary
    return (
        0 if summary.comparable else 1,
        -float(summary.quality_score_mean),
        -float(summary.confidence_level_mean),
        len(summary.mismatch_reasons),
        _normalize_text(entry.candidate_label),
        int(entry.candidate_index),
    )


def _matrix_benchmark_audit_entry_from_matrix_entry(
    entry: DeliberationCampaignMatrixComparisonEntry,
    *,
    rank: int,
) -> DeliberationCampaignMatrixBenchmarkAuditEntry:
    comparison_report = entry.comparison_bundle.comparison_report
    summary = comparison_report.summary
    return DeliberationCampaignMatrixBenchmarkAuditEntry(
        rank=rank,
        candidate_index=entry.candidate_index,
        candidate_label=_normalize_text(entry.candidate_label),
        candidate_campaign_id=_normalize_text(entry.candidate_campaign.campaign_id),
        runtime=_normalize_text(entry.candidate_spec.runtime),
        engine=_normalize_engine(entry.candidate_spec.engine_preference).value,
        comparison_id=comparison_report.comparison_id,
        comparable=bool(summary.comparable),
        mismatch_reasons=list(summary.mismatch_reasons),
        quality_score_mean=float(summary.quality_score_mean),
        confidence_level_mean=float(summary.confidence_level_mean),
        metadata={
            **dict(entry.metadata or {}),
            "comparison_key": summary.comparison_key_values[0] if len(summary.comparison_key_values) == 1 else None,
            "comparison_report_path": comparison_report.report_path,
        },
    )


def build_deliberation_campaign_matrix_benchmark_audit(
    benchmark_report: DeliberationCampaignMatrixBenchmarkBundle | dict[str, Any],
    *,
    include_markdown: bool = True,
) -> DeliberationCampaignMatrixBenchmarkAudit:
    report = (
        benchmark_report
        if isinstance(benchmark_report, DeliberationCampaignMatrixBenchmarkBundle)
        else DeliberationCampaignMatrixBenchmarkBundle.model_validate(benchmark_report)
    )
    ranked_entries = sorted(report.entries, key=_matrix_benchmark_audit_rank_key)
    audit_entries = [
        _matrix_benchmark_audit_entry_from_matrix_entry(entry, rank=index)
        for index, entry in enumerate(ranked_entries, start=1)
    ]
    comparable_count = sum(1 for entry in audit_entries if entry.comparable)
    mismatch_count = len(audit_entries) - comparable_count
    status_counts = Counter("comparable" if entry.comparable else "mismatch" for entry in audit_entries)
    quality_scores = [entry.quality_score_mean for entry in audit_entries]
    confidence_levels = [entry.confidence_level_mean for entry in audit_entries]
    candidate_labels = [entry.candidate_label for entry in audit_entries]
    candidate_campaign_ids = [entry.candidate_campaign_id for entry in audit_entries]
    comparison_ids = [entry.comparison_id for entry in audit_entries]
    runtime_values = _sorted_unique_values(entry.runtime for entry in audit_entries)
    engine_values = _sorted_unique_values(entry.engine for entry in audit_entries)
    mismatch_reasons = _sorted_unique_values(
        reason for entry in audit_entries for reason in entry.mismatch_reasons
    )
    best_candidate = audit_entries[0] if audit_entries else None
    worst_candidate = audit_entries[-1] if audit_entries else None
    audit = DeliberationCampaignMatrixBenchmarkAudit(
        benchmark_id=report.benchmark_id,
        created_at=report.created_at,
        output_dir=report.output_dir,
        benchmark_report_path=report.report_path,
        entries=audit_entries,
        summary=DeliberationCampaignMatrixBenchmarkAuditSummary(
            benchmark_id=report.benchmark_id,
            benchmark_report_path=report.report_path,
            baseline_campaign_id=report.baseline_campaign.campaign_id,
            baseline_runtime=_normalize_text(report.baseline_campaign.runtime_requested),
            baseline_engine=_normalize_text(report.baseline_campaign.engine_requested),
            candidate_count=len(audit_entries),
            comparable_count=comparable_count,
            mismatch_count=mismatch_count,
            status_counts=dict(status_counts),
            candidate_labels=candidate_labels,
            candidate_campaign_ids=candidate_campaign_ids,
            comparison_ids=comparison_ids,
            runtime_values=runtime_values,
            engine_values=engine_values,
            quality_score_mean=mean(quality_scores) if quality_scores else 0.0,
            quality_score_min=min(quality_scores) if quality_scores else 0.0,
            quality_score_max=max(quality_scores) if quality_scores else 0.0,
            confidence_level_mean=mean(confidence_levels) if confidence_levels else 0.0,
            confidence_level_min=min(confidence_levels) if confidence_levels else 0.0,
            confidence_level_max=max(confidence_levels) if confidence_levels else 0.0,
            best_candidate_rank=best_candidate.rank if best_candidate else 0,
            best_candidate_label=best_candidate.candidate_label if best_candidate else "",
            best_candidate_campaign_id=best_candidate.candidate_campaign_id if best_candidate else "",
            best_candidate_quality_score_mean=best_candidate.quality_score_mean if best_candidate else 0.0,
            best_candidate_confidence_level_mean=best_candidate.confidence_level_mean if best_candidate else 0.0,
            worst_candidate_rank=worst_candidate.rank if worst_candidate else 0,
            worst_candidate_label=worst_candidate.candidate_label if worst_candidate else "",
            worst_candidate_campaign_id=worst_candidate.candidate_campaign_id if worst_candidate else "",
            worst_candidate_quality_score_mean=worst_candidate.quality_score_mean if worst_candidate else 0.0,
            worst_candidate_confidence_level_mean=worst_candidate.confidence_level_mean if worst_candidate else 0.0,
            mismatch_reasons=mismatch_reasons,
            metadata={
                **report.metadata,
                "benchmark_report_path": report.report_path,
                "candidate_structure_key": report.summary.metadata.get("candidate_structure_key"),
                "candidate_count": len(audit_entries),
                "candidate_campaign_ids": candidate_campaign_ids,
                "candidate_labels": candidate_labels,
                "comparison_ids": comparison_ids,
                "best_candidate_rank": best_candidate.rank if best_candidate else None,
                "worst_candidate_rank": worst_candidate.rank if worst_candidate else None,
            },
        ),
        metadata={
            **report.metadata,
            "benchmark_report_path": report.report_path,
            "candidate_count": len(audit_entries),
            "comparable_count": comparable_count,
            "mismatch_count": mismatch_count,
            "best_candidate_label": best_candidate.candidate_label if best_candidate else None,
            "worst_candidate_label": worst_candidate.candidate_label if worst_candidate else None,
        },
    )
    if include_markdown:
        audit.markdown = render_deliberation_campaign_matrix_benchmark_markdown(audit)
    return audit


def load_deliberation_campaign_matrix_benchmark_audit(
    benchmark_id: str,
    *,
    output_dir: str | Path | None = None,
    include_markdown: bool = True,
) -> DeliberationCampaignMatrixBenchmarkAudit:
    report = load_deliberation_campaign_matrix_benchmark(benchmark_id, output_dir=output_dir)
    return build_deliberation_campaign_matrix_benchmark_audit(report, include_markdown=include_markdown)


def list_deliberation_campaign_matrix_benchmark_audits(
    *,
    output_dir: str | Path | None = None,
    limit: int | None = None,
    include_markdown: bool = False,
) -> list[DeliberationCampaignMatrixBenchmarkAudit]:
    benchmarks = list_deliberation_campaign_matrix_benchmarks(output_dir=output_dir, limit=limit)
    return [
        build_deliberation_campaign_matrix_benchmark_audit(benchmark, include_markdown=include_markdown)
        for benchmark in benchmarks
    ]


def build_deliberation_campaign_matrix_benchmark_export(
    benchmark_report: DeliberationCampaignMatrixBenchmarkBundle
    | DeliberationCampaignMatrixBenchmarkAudit
    | dict[str, Any],
    *,
    format: str = "markdown",
    include_content: bool = True,
) -> DeliberationCampaignMatrixBenchmarkExport:
    normalized_format = str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        raise ValueError("format must be one of: markdown, json")

    audit = (
        benchmark_report
        if isinstance(benchmark_report, DeliberationCampaignMatrixBenchmarkAudit)
        else build_deliberation_campaign_matrix_benchmark_audit(
            benchmark_report,
            include_markdown=normalized_format == "markdown",
        )
    )
    content = (
        render_deliberation_campaign_matrix_benchmark_markdown(audit)
        if normalized_format == "markdown"
        else json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True)
    )
    best_candidate_label = audit.summary.best_candidate_label
    worst_candidate_label = audit.summary.worst_candidate_label
    export = DeliberationCampaignMatrixBenchmarkExport(
        output_dir=audit.output_dir,
        benchmark_id=audit.benchmark_id,
        benchmark_report_path=audit.benchmark_report_path,
        format=normalized_format,
        candidate_count=audit.summary.candidate_count,
        candidate_labels=list(audit.summary.candidate_labels),
        candidate_campaign_ids=list(audit.summary.candidate_campaign_ids),
        comparison_ids=list(audit.summary.comparison_ids),
        comparable=audit.summary.mismatch_count == 0,
        comparable_count=audit.summary.comparable_count,
        mismatch_count=audit.summary.mismatch_count,
        mismatch_reasons=list(audit.summary.mismatch_reasons),
        quality_score_mean=audit.summary.quality_score_mean,
        confidence_level_mean=audit.summary.confidence_level_mean,
        best_candidate_label=best_candidate_label,
        worst_candidate_label=worst_candidate_label,
        best_candidate=(
            audit.entries[0].model_dump(mode="json")
            if audit.entries
            else None
        ),
        worst_candidate=(
            audit.entries[-1].model_dump(mode="json")
            if audit.entries
            else None
        ),
        content=content if include_content else None,
        metadata={
            **audit.metadata,
            "benchmark_id": audit.benchmark_id,
            "benchmark_report_path": audit.benchmark_report_path,
            "quality_score_mean": audit.summary.quality_score_mean,
            "confidence_level_mean": audit.summary.confidence_level_mean,
            "content_format": normalized_format,
            "content_kind": "markdown" if normalized_format == "markdown" else "json",
        },
    )
    return export


def materialize_deliberation_campaign_matrix_benchmark_export(
    benchmark_report: DeliberationCampaignMatrixBenchmarkBundle
    | DeliberationCampaignMatrixBenchmarkAudit
    | dict[str, Any],
    *,
    format: str = "markdown",
    output_dir: str | Path | None = None,
    export_id: str | None = None,
) -> DeliberationCampaignMatrixBenchmarkExport:
    export = build_deliberation_campaign_matrix_benchmark_export(
        benchmark_report,
        format=format,
        include_content=True,
    )
    if export_id:
        export.export_id = _normalize_text(export_id) or export.export_id
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR)
    export.output_dir = str(base_dir)
    export_dir = _matrix_benchmark_audit_export_dir(export.export_id, output_dir=base_dir)
    manifest_path = export_dir / "manifest.json"
    content_path = _matrix_benchmark_audit_export_content_path(
        export.export_id,
        output_dir=base_dir,
        format=export.format,
    )
    export_dir.mkdir(parents=True, exist_ok=True)
    export.manifest_path = str(manifest_path)
    export.content_path = str(content_path)
    export.metadata["manifest_path"] = str(manifest_path)
    export.metadata["content_path"] = str(content_path)
    export.metadata["persisted"] = True
    manifest_path.write_text(
        json.dumps(export.model_dump(mode="json", exclude={"content"}), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if export.content is not None:
        content_path.write_text(export.content, encoding="utf-8")
    return export


def load_deliberation_campaign_matrix_benchmark_export(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
    include_content: bool = True,
) -> DeliberationCampaignMatrixBenchmarkExport:
    manifest_path = _matrix_benchmark_audit_export_manifest_path(export_id, output_dir=output_dir)
    export = DeliberationCampaignMatrixBenchmarkExport.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    if include_content and export.content_path:
        content_path = Path(export.content_path)
        if content_path.is_file():
            export.content = content_path.read_text(encoding="utf-8")
    return export


def list_deliberation_campaign_matrix_benchmark_exports(
    *,
    output_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[DeliberationCampaignMatrixBenchmarkExport]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR)
    if not base_dir.exists():
        return []

    exports: list[DeliberationCampaignMatrixBenchmarkExport] = []
    for export_dir in base_dir.iterdir():
        if not export_dir.is_dir():
            continue
        manifest_path = export_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            export = DeliberationCampaignMatrixBenchmarkExport.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, json.JSONDecodeError):
            continue
        exports.append(export)

    exports.sort(
        key=lambda export: (
            _campaign_created_at_sort_key(export.created_at),
            export.export_id,
        ),
        reverse=True,
    )
    if limit is None:
        return exports
    return exports[: max(0, int(limit))]


def _matrix_benchmark_export_comparison_report_path(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR)
    return base_dir / comparison_id / "report.json"


def _matrix_benchmark_export_comparison_export_dir(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR)
    return base_dir / export_id


def _matrix_benchmark_export_comparison_export_manifest_path(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
) -> Path:
    return _matrix_benchmark_export_comparison_export_dir(export_id, output_dir=output_dir) / "manifest.json"


def _matrix_benchmark_export_comparison_export_content_path(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> Path:
    extension = ".md" if str(format).strip().lower() == "markdown" else ".json"
    return _matrix_benchmark_export_comparison_export_dir(export_id, output_dir=output_dir) / f"content{extension}"


def compare_deliberation_campaign_matrix_benchmark_exports(
    *,
    export_ids: list[str] | None = None,
    latest: int | None = None,
    output_dir: str | Path | None = None,
    persist: bool = False,
    comparison_output_dir: str | Path | None = None,
) -> DeliberationCampaignMatrixBenchmarkExportComparisonReport:
    selected_exports = _selected_deliberation_campaign_matrix_benchmark_exports(
        export_ids=export_ids,
        latest=latest,
        output_dir=output_dir,
    )
    if len(selected_exports) < 2:
        raise ValueError("At least two matrix benchmark exports are required for comparison.")
    entries = [_matrix_benchmark_export_comparison_entry_from_export(export) for export in selected_exports]
    summary = _matrix_benchmark_export_comparison_summary_from_entries(entries, selected_exports)
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR)
    comparison_base_dir = Path(
        comparison_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR
    )
    requested_export_ids = [_normalize_text(export_id) for export_id in (export_ids or []) if _normalize_text(export_id)]
    report = DeliberationCampaignMatrixBenchmarkExportComparisonReport(
        output_dir=str(base_dir),
        requested_export_ids=requested_export_ids,
        latest=latest,
        entries=entries,
        summary=summary,
        metadata={
            "output_dir": str(base_dir),
            "requested_export_ids": requested_export_ids,
            "latest": latest,
            "selected_export_ids": [entry.export_id for entry in entries],
            "candidate_structure_key": summary.candidate_structure_key_values[0]
            if len(summary.candidate_structure_key_values) == 1
            else None,
        },
    )
    if persist:
        comparison_base_dir.mkdir(parents=True, exist_ok=True)
        comparison_path = _matrix_benchmark_export_comparison_report_path(
            report.comparison_id,
            output_dir=comparison_base_dir,
        )
        comparison_path.parent.mkdir(parents=True, exist_ok=True)
        report.report_path = str(comparison_path)
        report.metadata["report_path"] = str(comparison_path)
        report.metadata["persisted"] = True
        comparison_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report


def load_deliberation_campaign_matrix_benchmark_export_comparison_report(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
) -> DeliberationCampaignMatrixBenchmarkExportComparisonReport:
    report_path = _matrix_benchmark_export_comparison_report_path(comparison_id, output_dir=output_dir)
    return DeliberationCampaignMatrixBenchmarkExportComparisonReport.model_validate_json(
        report_path.read_text(encoding="utf-8")
    )


def list_deliberation_campaign_matrix_benchmark_export_comparison_reports(
    *,
    output_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[DeliberationCampaignMatrixBenchmarkExportComparisonReport]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR)
    if not base_dir.exists():
        return []

    reports: list[DeliberationCampaignMatrixBenchmarkExportComparisonReport] = []
    for comparison_dir in base_dir.iterdir():
        if not comparison_dir.is_dir():
            continue
        report_path = comparison_dir / "report.json"
        if not report_path.is_file():
            continue
        try:
            report = DeliberationCampaignMatrixBenchmarkExportComparisonReport.model_validate_json(
                report_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, json.JSONDecodeError):
            continue
        reports.append(report)

    reports.sort(
        key=lambda report: (
            _campaign_created_at_sort_key(report.created_at),
            report.comparison_id,
        ),
        reverse=True,
    )
    if limit is None:
        return reports
    return reports[: max(0, int(limit))]


def build_deliberation_campaign_matrix_benchmark_export_comparison_audit(
    comparison_report: DeliberationCampaignMatrixBenchmarkExportComparisonReport | dict[str, Any],
    *,
    include_markdown: bool = True,
) -> DeliberationCampaignMatrixBenchmarkExportComparisonAudit:
    report = (
        comparison_report
        if isinstance(comparison_report, DeliberationCampaignMatrixBenchmarkExportComparisonReport)
        else DeliberationCampaignMatrixBenchmarkExportComparisonReport.model_validate(comparison_report)
    )
    summary = report.summary
    audit = DeliberationCampaignMatrixBenchmarkExportComparisonAudit(
        comparison_id=report.comparison_id,
        created_at=report.created_at,
        output_dir=report.output_dir,
        report_path=report.report_path,
        requested_export_ids=list(report.requested_export_ids),
        latest=report.latest,
        export_count=summary.export_count,
        export_ids=list(summary.export_ids),
        comparable=summary.comparable,
        mismatch_reasons=list(summary.mismatch_reasons),
        entries=list(report.entries),
        summary=summary,
        metadata={
            **report.metadata,
            "report_path": report.report_path,
            "candidate_structure_key": (
                summary.candidate_structure_key_values[0]
                if len(summary.candidate_structure_key_values) == 1
                else None
            ),
            "entry_count": len(report.entries),
        },
    )
    if include_markdown:
        audit.markdown = render_deliberation_campaign_matrix_benchmark_export_comparison_markdown(audit)
    return audit


def load_deliberation_campaign_matrix_benchmark_export_comparison_audit(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
    include_markdown: bool = True,
) -> DeliberationCampaignMatrixBenchmarkExportComparisonAudit:
    report = load_deliberation_campaign_matrix_benchmark_export_comparison_report(
        comparison_id,
        output_dir=output_dir,
    )
    return build_deliberation_campaign_matrix_benchmark_export_comparison_audit(
        report,
        include_markdown=include_markdown,
    )


def build_deliberation_campaign_matrix_benchmark_export_comparison_export(
    comparison_report: DeliberationCampaignMatrixBenchmarkExportComparisonReport
    | DeliberationCampaignMatrixBenchmarkExportComparisonAudit
    | dict[str, Any],
    *,
    format: str = "markdown",
    include_content: bool = True,
) -> DeliberationCampaignMatrixBenchmarkExportComparisonExport:
    normalized_format = str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        raise ValueError("format must be one of: markdown, json")

    audit = (
        comparison_report
        if isinstance(comparison_report, DeliberationCampaignMatrixBenchmarkExportComparisonAudit)
        else build_deliberation_campaign_matrix_benchmark_export_comparison_audit(
            comparison_report,
            include_markdown=normalized_format == "markdown",
        )
    )
    content = (
        render_deliberation_campaign_matrix_benchmark_export_comparison_markdown(audit)
        if normalized_format == "markdown"
        else json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True)
    )
    export = DeliberationCampaignMatrixBenchmarkExportComparisonExport(
        output_dir=audit.output_dir,
        comparison_id=audit.comparison_id,
        comparison_report_path=audit.report_path,
        format=normalized_format,
        export_count=audit.export_count,
        export_ids=list(audit.export_ids),
        comparable=audit.comparable,
        mismatch_reasons=list(audit.mismatch_reasons),
        content=content if include_content else None,
        metadata={
            **audit.metadata,
            "comparison_id": audit.comparison_id,
            "comparison_report_path": audit.report_path,
            "content_format": normalized_format,
            "content_kind": "markdown" if normalized_format == "markdown" else "json",
        },
    )
    return export


def materialize_deliberation_campaign_matrix_benchmark_export_comparison_export(
    comparison_report: DeliberationCampaignMatrixBenchmarkExportComparisonReport
    | DeliberationCampaignMatrixBenchmarkExportComparisonAudit
    | dict[str, Any],
    *,
    format: str = "markdown",
    output_dir: str | Path | None = None,
    export_id: str | None = None,
) -> DeliberationCampaignMatrixBenchmarkExportComparisonExport:
    export = build_deliberation_campaign_matrix_benchmark_export_comparison_export(
        comparison_report,
        format=format,
        include_content=True,
    )
    if export_id:
        export.export_id = _normalize_text(export_id) or export.export_id
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR)
    export.output_dir = str(base_dir)
    export_dir = _matrix_benchmark_export_comparison_export_dir(export.export_id, output_dir=base_dir)
    manifest_path = _matrix_benchmark_export_comparison_export_manifest_path(
        export.export_id,
        output_dir=base_dir,
    )
    content_path = _matrix_benchmark_export_comparison_export_content_path(
        export.export_id,
        output_dir=base_dir,
        format=export.format,
    )
    export_dir.mkdir(parents=True, exist_ok=True)
    export.manifest_path = str(manifest_path)
    export.content_path = str(content_path)
    export.metadata["manifest_path"] = str(manifest_path)
    export.metadata["content_path"] = str(content_path)
    export.metadata["persisted"] = True
    manifest_path.write_text(
        json.dumps(export.model_dump(mode="json", exclude={"content"}), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if export.content is not None:
        content_path.write_text(export.content, encoding="utf-8")
    return export


def load_deliberation_campaign_matrix_benchmark_export_comparison_export(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
    include_content: bool = True,
) -> DeliberationCampaignMatrixBenchmarkExportComparisonExport:
    manifest_path = _matrix_benchmark_export_comparison_export_manifest_path(export_id, output_dir=output_dir)
    export = DeliberationCampaignMatrixBenchmarkExportComparisonExport.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    if include_content and export.content_path:
        content_path = Path(export.content_path)
        if content_path.is_file():
            export.content = content_path.read_text(encoding="utf-8")
    return export


def list_deliberation_campaign_matrix_benchmark_export_comparison_exports(
    *,
    output_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[DeliberationCampaignMatrixBenchmarkExportComparisonExport]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR)
    if not base_dir.exists():
        return []

    exports: list[DeliberationCampaignMatrixBenchmarkExportComparisonExport] = []
    for export_dir in base_dir.iterdir():
        if not export_dir.is_dir():
            continue
        manifest_path = export_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            export = DeliberationCampaignMatrixBenchmarkExportComparisonExport.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, json.JSONDecodeError):
            continue
        exports.append(export)

    exports.sort(
        key=lambda export: (
            _campaign_created_at_sort_key(export.created_at),
            export.export_id,
        ),
        reverse=True,
    )
    if limit is None:
        return exports
    return exports[: max(0, int(limit))]


def render_deliberation_campaign_matrix_benchmark_export_comparison_markdown(
    comparison_report: DeliberationCampaignMatrixBenchmarkExportComparisonReport
    | DeliberationCampaignMatrixBenchmarkExportComparisonAudit
    | dict[str, Any],
) -> str:
    audit = (
        comparison_report
        if isinstance(comparison_report, DeliberationCampaignMatrixBenchmarkExportComparisonAudit)
        else build_deliberation_campaign_matrix_benchmark_export_comparison_audit(
            comparison_report,
            include_markdown=False,
        )
    )
    requested_export_ids = ", ".join(audit.requested_export_ids) if audit.requested_export_ids else "n/a"
    export_ids = ", ".join(audit.export_ids) if audit.export_ids else "n/a"
    benchmark_ids = ", ".join(audit.summary.benchmark_ids) if audit.summary.benchmark_ids else "n/a"
    format_values = ", ".join(audit.summary.format_values) if audit.summary.format_values else "n/a"
    mismatch_reasons = ", ".join(audit.mismatch_reasons) if audit.mismatch_reasons else "none"
    summary = audit.summary
    lines = [
        "# Deliberation Campaign Matrix Benchmark Export Comparison",
        f"- Comparison ID: {audit.comparison_id}",
        f"- Created At: {audit.created_at.isoformat()}",
        f"- Output Dir: {audit.output_dir}",
        f"- Report Path: {audit.report_path or 'n/a'}",
        f"- Requested Export IDs: {requested_export_ids}",
        f"- Latest: {audit.latest if audit.latest is not None else 'n/a'}",
        f"- Comparable: {'yes' if audit.comparable else 'no'}",
        f"- Mismatch Reasons: {mismatch_reasons}",
        f"- Export Count: {audit.export_count}",
        f"- Export IDs: {export_ids}",
        f"- Benchmark IDs: {benchmark_ids}",
        f"- Formats: {format_values}",
        "",
        "## Aggregate Metrics",
        f"- Quality Score Mean: {summary.quality_score_mean:.3f} (min {summary.quality_score_min:.3f}, max {summary.quality_score_max:.3f})",
        f"- Confidence Level Mean: {summary.confidence_level_mean:.3f} (min {summary.confidence_level_min:.3f}, max {summary.confidence_level_max:.3f})",
        f"- Comparable Exports: {summary.comparable_export_count}",
        f"- Mismatched Exports: {summary.mismatch_export_count}",
        f"- Candidates Total: {summary.candidate_count_total}",
        f"- Comparable Candidates: {summary.comparable_candidate_total}",
        f"- Mismatched Candidates: {summary.mismatch_candidate_total}",
    ]
    if audit.entries:
        lines.extend(
            [
                "",
                "## Entries",
                "| Export ID | Benchmark ID | Format | Candidates | Comparable | Score | Confidence | Best Candidate | Worst Candidate |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for entry in audit.entries:
            lines.append(
                "| "
                + " | ".join(
                    [
                        entry.export_id,
                        entry.benchmark_id,
                        entry.format,
                        str(entry.candidate_count),
                        "yes" if entry.comparable else "no",
                        f"{entry.quality_score_mean:.3f}",
                        f"{entry.confidence_level_mean:.3f}",
                        entry.best_candidate_label or "n/a",
                        entry.worst_candidate_label or "n/a",
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def compare_deliberation_campaign_matrix_benchmark_export_comparison_bundle(
    *,
    export_ids: list[str] | None = None,
    latest: int | None = None,
    output_dir: str | Path | None = None,
    persist: bool = True,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
    format: str = "markdown",
    export_id: str | None = None,
) -> DeliberationCampaignMatrixBenchmarkExportComparisonBundle:
    normalized_format = str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        raise ValueError("format must be one of: markdown, json")

    comparison_report = compare_deliberation_campaign_matrix_benchmark_exports(
        export_ids=export_ids,
        latest=latest,
        output_dir=output_dir,
        persist=persist,
        comparison_output_dir=comparison_output_dir,
    )
    audit = build_deliberation_campaign_matrix_benchmark_export_comparison_audit(
        comparison_report,
        include_markdown=normalized_format == "markdown",
    )
    export = materialize_deliberation_campaign_matrix_benchmark_export_comparison_export(
        audit,
        format=normalized_format,
        output_dir=export_output_dir,
        export_id=_normalize_text(export_id) or f"{comparison_report.comparison_id}__{normalized_format}",
    )
    return DeliberationCampaignMatrixBenchmarkExportComparisonBundle(
        comparison_report=comparison_report,
        audit=audit,
        export=export,
        metadata={
            "export_ids": list(export_ids or []),
            "latest": latest,
            "persisted": persist,
            "comparison_output_dir": str(
                Path(
                    comparison_output_dir
                    or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR
                )
            ),
            "export_output_dir": str(
                Path(
                    export_output_dir
                    or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR
                )
            ),
            "format": normalized_format,
            "comparison_id": comparison_report.comparison_id,
            "export_id": export.export_id,
        },
    )


def compare_deliberation_campaign_matrix_benchmarks(
    *,
    benchmark_ids: list[str] | None = None,
    latest: int | None = None,
    output_dir: str | Path | None = None,
    persist: bool = False,
    comparison_output_dir: str | Path | None = None,
) -> DeliberationCampaignMatrixBenchmarkComparisonReport:
    selected_benchmarks = _selected_deliberation_campaign_matrix_benchmarks(
        benchmark_ids=benchmark_ids,
        latest=latest,
        output_dir=output_dir,
    )
    if len(selected_benchmarks) < 2:
        raise ValueError("At least two matrix benchmark reports are required for comparison.")
    entries = [_matrix_benchmark_comparison_entry_from_report(report) for report in selected_benchmarks]
    summary = _matrix_benchmark_comparison_summary_from_entries(entries, selected_benchmarks)
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR)
    comparison_base_dir = Path(
        comparison_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR
    )
    requested_benchmark_ids = [
        _normalize_text(benchmark_id)
        for benchmark_id in (benchmark_ids or [])
        if _normalize_text(benchmark_id)
    ]
    report = DeliberationCampaignMatrixBenchmarkComparisonReport(
        output_dir=str(base_dir),
        requested_benchmark_ids=requested_benchmark_ids,
        latest=latest,
        entries=entries,
        summary=summary,
        metadata={
            "output_dir": str(base_dir),
            "requested_benchmark_ids": requested_benchmark_ids,
            "latest": latest,
            "selected_benchmark_ids": [entry.benchmark_id for entry in entries],
            "candidate_structure_key": summary.candidate_structure_key_values[0]
            if len(summary.candidate_structure_key_values) == 1
            else None,
        },
    )
    if persist:
        comparison_base_dir.mkdir(parents=True, exist_ok=True)
        comparison_path = _matrix_benchmark_comparison_report_path(
            report.comparison_id,
            output_dir=comparison_base_dir,
        )
        comparison_path.parent.mkdir(parents=True, exist_ok=True)
        report.report_path = str(comparison_path)
        report.metadata["report_path"] = str(comparison_path)
        report.metadata["persisted"] = True
        comparison_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report


def load_deliberation_campaign_matrix_benchmark_comparison_report(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
) -> DeliberationCampaignMatrixBenchmarkComparisonReport:
    report_path = _matrix_benchmark_comparison_report_path(comparison_id, output_dir=output_dir)
    return DeliberationCampaignMatrixBenchmarkComparisonReport.model_validate_json(
        report_path.read_text(encoding="utf-8")
    )


def list_deliberation_campaign_matrix_benchmark_comparison_reports(
    *,
    output_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[DeliberationCampaignMatrixBenchmarkComparisonReport]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR)
    if not base_dir.exists():
        return []

    reports: list[DeliberationCampaignMatrixBenchmarkComparisonReport] = []
    for comparison_dir in base_dir.iterdir():
        if not comparison_dir.is_dir():
            continue
        report_path = comparison_dir / "report.json"
        if not report_path.is_file():
            continue
        try:
            report = DeliberationCampaignMatrixBenchmarkComparisonReport.model_validate_json(
                report_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, json.JSONDecodeError):
            continue
        reports.append(report)

    reports.sort(
        key=lambda report: (
            _campaign_created_at_sort_key(report.created_at),
            report.comparison_id,
        ),
        reverse=True,
    )
    if limit is None:
        return reports
    return reports[: max(0, int(limit))]


def _matrix_benchmark_comparison_export_dir(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR)
    return base_dir / export_id


def _matrix_benchmark_comparison_export_manifest_path(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
) -> Path:
    return _matrix_benchmark_comparison_export_dir(export_id, output_dir=output_dir) / "manifest.json"


def _matrix_benchmark_comparison_export_content_path(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> Path:
    extension = ".md" if str(format).strip().lower() == "markdown" else ".json"
    return _matrix_benchmark_comparison_export_dir(export_id, output_dir=output_dir) / f"content{extension}"


def build_deliberation_campaign_matrix_benchmark_comparison_audit(
    comparison_report: DeliberationCampaignMatrixBenchmarkComparisonReport | dict[str, Any],
    *,
    include_markdown: bool = True,
) -> DeliberationCampaignMatrixBenchmarkComparisonAudit:
    report = (
        comparison_report
        if isinstance(comparison_report, DeliberationCampaignMatrixBenchmarkComparisonReport)
        else DeliberationCampaignMatrixBenchmarkComparisonReport.model_validate(comparison_report)
    )
    summary = report.summary
    audit = DeliberationCampaignMatrixBenchmarkComparisonAudit(
        comparison_id=report.comparison_id,
        created_at=report.created_at,
        output_dir=report.output_dir,
        report_path=report.report_path,
        requested_benchmark_ids=list(report.requested_benchmark_ids),
        latest=report.latest,
        benchmark_count=summary.benchmark_count,
        benchmark_ids=list(summary.benchmark_ids),
        comparable=summary.comparable,
        mismatch_reasons=list(summary.mismatch_reasons),
        entries=list(report.entries),
        summary=summary,
        metadata={
            **report.metadata,
            "report_path": report.report_path,
            "candidate_structure_key": (
                summary.candidate_structure_key_values[0] if len(summary.candidate_structure_key_values) == 1 else None
            ),
            "entry_count": len(report.entries),
        },
    )
    if include_markdown:
        audit.markdown = render_deliberation_campaign_matrix_benchmark_comparison_markdown(audit)
    return audit


def load_deliberation_campaign_matrix_benchmark_comparison_audit(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
    include_markdown: bool = True,
) -> DeliberationCampaignMatrixBenchmarkComparisonAudit:
    report = load_deliberation_campaign_matrix_benchmark_comparison_report(comparison_id, output_dir=output_dir)
    return build_deliberation_campaign_matrix_benchmark_comparison_audit(
        report,
        include_markdown=include_markdown,
    )


def build_deliberation_campaign_matrix_benchmark_comparison_export(
    comparison_report: DeliberationCampaignMatrixBenchmarkComparisonReport
    | DeliberationCampaignMatrixBenchmarkComparisonAudit
    | dict[str, Any],
    *,
    format: str = "markdown",
    include_content: bool = True,
) -> DeliberationCampaignMatrixBenchmarkComparisonExport:
    normalized_format = str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        raise ValueError("format must be one of: markdown, json")

    audit = (
        comparison_report
        if isinstance(comparison_report, DeliberationCampaignMatrixBenchmarkComparisonAudit)
        else build_deliberation_campaign_matrix_benchmark_comparison_audit(
            comparison_report,
            include_markdown=normalized_format == "markdown",
        )
    )
    content = (
        render_deliberation_campaign_matrix_benchmark_comparison_markdown(audit)
        if normalized_format == "markdown"
        else json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True)
    )
    export = DeliberationCampaignMatrixBenchmarkComparisonExport(
        output_dir=audit.output_dir,
        comparison_id=audit.comparison_id,
        comparison_report_path=audit.report_path,
        format=normalized_format,
        benchmark_count=audit.benchmark_count,
        benchmark_ids=list(audit.benchmark_ids),
        comparable=audit.comparable,
        mismatch_reasons=list(audit.mismatch_reasons),
        content=content if include_content else None,
        metadata={
            **audit.metadata,
            "comparison_id": audit.comparison_id,
            "comparison_report_path": audit.report_path,
            "content_format": normalized_format,
            "content_kind": "markdown" if normalized_format == "markdown" else "json",
        },
    )
    return export


def materialize_deliberation_campaign_matrix_benchmark_comparison_export(
    comparison_report: DeliberationCampaignMatrixBenchmarkComparisonReport
    | DeliberationCampaignMatrixBenchmarkComparisonAudit
    | dict[str, Any],
    *,
    format: str = "markdown",
    output_dir: str | Path | None = None,
    export_id: str | None = None,
) -> DeliberationCampaignMatrixBenchmarkComparisonExport:
    export = build_deliberation_campaign_matrix_benchmark_comparison_export(
        comparison_report,
        format=format,
        include_content=True,
    )
    if export_id:
        export.export_id = _normalize_text(export_id) or export.export_id
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR)
    export.output_dir = str(base_dir)
    export_dir = _matrix_benchmark_comparison_export_dir(export.export_id, output_dir=base_dir)
    manifest_path = export_dir / "manifest.json"
    content_path = _matrix_benchmark_comparison_export_content_path(
        export.export_id,
        output_dir=base_dir,
        format=export.format,
    )
    export_dir.mkdir(parents=True, exist_ok=True)
    export.manifest_path = str(manifest_path)
    export.content_path = str(content_path)
    export.metadata["manifest_path"] = str(manifest_path)
    export.metadata["content_path"] = str(content_path)
    export.metadata["persisted"] = True
    manifest_path.write_text(
        json.dumps(export.model_dump(mode="json", exclude={"content"}), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if export.content is not None:
        content_path.write_text(export.content, encoding="utf-8")
    return export


def load_deliberation_campaign_matrix_benchmark_comparison_export(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
    include_content: bool = True,
) -> DeliberationCampaignMatrixBenchmarkComparisonExport:
    manifest_path = _matrix_benchmark_comparison_export_manifest_path(export_id, output_dir=output_dir)
    export = DeliberationCampaignMatrixBenchmarkComparisonExport.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    if include_content and export.content_path:
        content_path = Path(export.content_path)
        if content_path.is_file():
            export.content = content_path.read_text(encoding="utf-8")
    return export


def list_deliberation_campaign_matrix_benchmark_comparison_exports(
    *,
    output_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[DeliberationCampaignMatrixBenchmarkComparisonExport]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR)
    if not base_dir.exists():
        return []

    exports: list[DeliberationCampaignMatrixBenchmarkComparisonExport] = []
    for export_dir in base_dir.iterdir():
        if not export_dir.is_dir():
            continue
        manifest_path = export_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            export = DeliberationCampaignMatrixBenchmarkComparisonExport.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, json.JSONDecodeError):
            continue
        exports.append(export)

    exports.sort(
        key=lambda export: (
            _campaign_created_at_sort_key(export.created_at),
            export.export_id,
        ),
        reverse=True,
    )
    if limit is None:
        return exports
    return exports[: max(0, int(limit))]


def render_deliberation_campaign_matrix_benchmark_comparison_markdown(
    comparison_report: DeliberationCampaignMatrixBenchmarkComparisonReport
    | DeliberationCampaignMatrixBenchmarkComparisonAudit
    | dict[str, Any],
) -> str:
    audit = (
        comparison_report
        if isinstance(comparison_report, DeliberationCampaignMatrixBenchmarkComparisonAudit)
        else build_deliberation_campaign_matrix_benchmark_comparison_audit(comparison_report, include_markdown=False)
    )
    requested_benchmark_ids = ", ".join(audit.requested_benchmark_ids) if audit.requested_benchmark_ids else "n/a"
    benchmark_ids = ", ".join(audit.benchmark_ids) if audit.benchmark_ids else "n/a"
    mismatch_reasons = ", ".join(audit.mismatch_reasons) if audit.mismatch_reasons else "none"
    summary = audit.summary
    lines = [
        "# Deliberation Campaign Matrix Benchmark Comparison",
        f"- Comparison ID: {audit.comparison_id}",
        f"- Created At: {audit.created_at.isoformat()}",
        f"- Output Dir: {audit.output_dir}",
        f"- Report Path: {audit.report_path or 'n/a'}",
        f"- Requested Benchmark IDs: {requested_benchmark_ids}",
        f"- Latest: {audit.latest if audit.latest is not None else 'n/a'}",
        f"- Comparable: {'yes' if audit.comparable else 'no'}",
        f"- Mismatch Reasons: {mismatch_reasons}",
        f"- Benchmark Count: {audit.benchmark_count}",
        f"- Benchmark IDs: {benchmark_ids}",
        "",
        "## Aggregate Metrics",
        f"- Quality Score Mean: {summary.quality_score_mean:.3f} (min {summary.quality_score_min:.3f}, max {summary.quality_score_max:.3f})",
        f"- Confidence Level Mean: {summary.confidence_level_mean:.3f} (min {summary.confidence_level_min:.3f}, max {summary.confidence_level_max:.3f})",
        f"- Candidates Total: {summary.candidate_count_total}",
        f"- Comparable Candidates: {summary.comparable_count_total}",
        f"- Mismatched Candidates: {summary.mismatch_count_total}",
    ]
    if audit.entries:
        lines.extend(
            [
                "",
                "## Entries",
                "| Benchmark ID | Topic | Mode | Baseline Runtime | Baseline Engine | Candidates | Comparable | Mismatch | Score | Confidence |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for entry in audit.entries:
            lines.append(
                "| "
                + " | ".join(
                    [
                        entry.benchmark_id,
                        entry.topic,
                        entry.mode,
                        entry.baseline_runtime,
                        entry.baseline_engine,
                        f"{entry.comparable_count}/{entry.candidate_count}",
                        str(entry.comparable_count),
                        str(entry.mismatch_count),
                        f"{entry.quality_score_mean:.3f}",
                        f"{entry.confidence_level_mean:.3f}",
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def compare_deliberation_campaign_matrix_benchmark_comparison_bundle(
    *,
    benchmark_ids: list[str] | None = None,
    latest: int | None = None,
    output_dir: str | Path | None = None,
    persist: bool = True,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
    format: str = "markdown",
    export_id: str | None = None,
) -> DeliberationCampaignMatrixBenchmarkComparisonBundle:
    normalized_format = str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        raise ValueError("format must be one of: markdown, json")

    comparison_report = compare_deliberation_campaign_matrix_benchmarks(
        benchmark_ids=benchmark_ids,
        latest=latest,
        output_dir=output_dir,
        persist=persist,
        comparison_output_dir=comparison_output_dir,
    )
    audit = build_deliberation_campaign_matrix_benchmark_comparison_audit(
        comparison_report,
        include_markdown=normalized_format == "markdown",
    )
    export = materialize_deliberation_campaign_matrix_benchmark_comparison_export(
        audit,
        format=normalized_format,
        output_dir=export_output_dir,
        export_id=_normalize_text(export_id) or f"{comparison_report.comparison_id}__{normalized_format}",
    )
    return DeliberationCampaignMatrixBenchmarkComparisonBundle(
        comparison_report=comparison_report,
        audit=audit,
        export=export,
        metadata={
            "benchmark_ids": list(benchmark_ids or []),
            "latest": latest,
            "persisted": persist,
            "comparison_output_dir": str(
                Path(comparison_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR)
            ),
            "export_output_dir": str(
                Path(export_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR)
            ),
            "format": normalized_format,
            "comparison_id": comparison_report.comparison_id,
            "export_id": export.export_id,
        },
    )


def _campaign_report_overview(report: DeliberationCampaignReport) -> dict[str, Any]:
    summary = report.summary
    stability_summary = getattr(summary, "campaign_stability_summary", None)
    comparison_key = ""
    if stability_summary is not None:
        comparison_key = _normalize_text(getattr(stability_summary, "comparison_key", ""))
    if not comparison_key:
        comparison_key = _normalize_text(report.metadata.get("comparison_key"))
    summary_metadata = getattr(summary, "metadata", {}) if hasattr(summary, "metadata") else {}
    if isinstance(summary_metadata, dict) and not comparison_key:
        comparison_key = _normalize_text(summary_metadata.get("comparison_key"))
    return {
        "campaign_id": report.campaign_id,
        "status": report.status.value,
        "created_at": report.created_at.isoformat(),
        "topic": report.topic,
        "objective": report.objective,
        "mode": report.mode.value,
        "runtime_requested": report.runtime_requested,
        "engine_requested": report.engine_requested,
        "sample_count_requested": report.sample_count_requested,
        "sample_count_completed": summary.sample_count_completed,
        "sample_count_failed": summary.sample_count_failed,
        "fallback_guard_applied": report.fallback_guard_applied,
        "fallback_guard_reason": report.fallback_guard_reason,
        "report_path": report.report_path,
        "comparison_key": comparison_key,
    }


def _comparison_report_overview(report: DeliberationCampaignComparisonReport) -> dict[str, Any]:
    summary = report.summary
    return {
        "comparison_id": report.comparison_id,
        "created_at": report.created_at.isoformat(),
        "latest": report.latest,
        "requested_campaign_ids": list(report.requested_campaign_ids),
        "campaign_count": summary.campaign_count,
        "campaign_ids": list(summary.campaign_ids),
        "comparable": summary.comparable,
        "mismatch_reasons": list(summary.mismatch_reasons),
        "comparison_key": summary.comparison_key_values[0] if summary.comparison_key_values else report.metadata.get("comparison_key"),
        "report_path": report.report_path,
    }


def _comparison_export_overview(export: DeliberationCampaignComparisonExport) -> dict[str, Any]:
    return {
        "export_id": export.export_id,
        "created_at": export.created_at.isoformat(),
        "output_dir": export.output_dir,
        "comparison_id": export.comparison_id,
        "comparison_report_path": export.comparison_report_path,
        "format": export.format,
        "campaign_count": export.campaign_count,
        "campaign_ids": list(export.campaign_ids),
        "comparable": export.comparable,
        "mismatch_reasons": list(export.mismatch_reasons),
        "manifest_path": export.manifest_path,
        "content_path": export.content_path,
    }


def _benchmark_report_overview(benchmark: DeliberationCampaignBenchmarkBundle) -> dict[str, Any]:
    comparison_bundle = benchmark.comparison_bundle
    comparison_report = comparison_bundle.comparison_report
    export = comparison_bundle.export
    return {
        "benchmark_id": benchmark.benchmark_id,
        "created_at": benchmark.created_at.isoformat(),
        "output_dir": benchmark.output_dir,
        "report_path": benchmark.report_path,
        "baseline_campaign_id": benchmark.baseline_campaign.campaign_id,
        "candidate_campaign_id": benchmark.candidate_campaign.campaign_id,
        "comparison_id": comparison_report.comparison_id,
        "export_id": export.export_id,
        "format": export.format,
        "comparison_report_path": comparison_report.report_path,
        "audit_report_path": comparison_bundle.audit.report_path,
        "export_manifest_path": export.manifest_path,
        "export_content_path": export.content_path,
    }


def _matrix_benchmark_report_overview(benchmark: DeliberationCampaignMatrixBenchmarkBundle) -> dict[str, Any]:
    return {
        "benchmark_id": benchmark.benchmark_id,
        "created_at": benchmark.created_at.isoformat(),
        "output_dir": benchmark.output_dir,
        "report_path": benchmark.report_path,
        "baseline_campaign_id": benchmark.baseline_campaign.campaign_id,
        "candidate_count": benchmark.summary.candidate_count,
        "candidate_campaign_ids": list(benchmark.summary.candidate_campaign_ids),
        "candidate_labels": list(benchmark.summary.candidate_labels),
        "comparison_ids": list(benchmark.summary.comparison_ids),
        "comparable_count": benchmark.summary.comparable_count,
        "mismatch_count": benchmark.summary.mismatch_count,
        "quality_score_mean": benchmark.summary.quality_score_mean,
        "confidence_level_mean": benchmark.summary.confidence_level_mean,
    }


def _matrix_benchmark_audit_overview(audit: DeliberationCampaignMatrixBenchmarkAudit) -> dict[str, Any]:
    summary = audit.summary
    return {
        "benchmark_id": audit.benchmark_id,
        "created_at": audit.created_at.isoformat(),
        "output_dir": audit.output_dir,
        "benchmark_report_path": audit.benchmark_report_path,
        "candidate_count": summary.candidate_count,
        "comparable_count": summary.comparable_count,
        "mismatch_count": summary.mismatch_count,
        "best_candidate_label": summary.best_candidate_label,
        "worst_candidate_label": summary.worst_candidate_label,
        "quality_score_mean": summary.quality_score_mean,
        "confidence_level_mean": summary.confidence_level_mean,
    }


def _matrix_benchmark_export_overview(export: DeliberationCampaignMatrixBenchmarkExport) -> dict[str, Any]:
    return {
        "export_id": getattr(export, "export_id", None),
        "created_at": (
            getattr(export, "created_at", None).isoformat()
            if isinstance(getattr(export, "created_at", None), datetime)
            else getattr(export, "created_at", None)
        ),
        "output_dir": getattr(export, "output_dir", None),
        "benchmark_id": getattr(export, "benchmark_id", None),
        "benchmark_report_path": getattr(export, "benchmark_report_path", None),
        "format": getattr(export, "format", None),
        "candidate_count": getattr(export, "candidate_count", 0),
        "candidate_labels": list(getattr(export, "candidate_labels", []) or []),
        "candidate_campaign_ids": list(getattr(export, "candidate_campaign_ids", []) or []),
        "comparison_ids": list(getattr(export, "comparison_ids", []) or []),
        "comparable": getattr(export, "comparable", None),
        "comparable_count": getattr(export, "comparable_count", 0),
        "mismatch_count": getattr(export, "mismatch_count", 0),
        "mismatch_reasons": list(getattr(export, "mismatch_reasons", []) or []),
        "quality_score_mean": getattr(export, "quality_score_mean", None),
        "confidence_level_mean": getattr(export, "confidence_level_mean", None),
        "best_candidate_label": getattr(export, "best_candidate_label", None),
        "worst_candidate_label": getattr(export, "worst_candidate_label", None),
        "manifest_path": getattr(export, "manifest_path", None),
        "content_path": getattr(export, "content_path", None),
    }


def _matrix_benchmark_export_comparison_report_overview(
    report: DeliberationCampaignMatrixBenchmarkExportComparisonReport,
) -> dict[str, Any]:
    summary = report.summary
    return {
        "comparison_id": report.comparison_id,
        "created_at": report.created_at.isoformat(),
        "latest": report.latest,
        "requested_export_ids": list(report.requested_export_ids),
        "export_count": summary.export_count,
        "export_ids": list(summary.export_ids),
        "benchmark_ids": list(summary.benchmark_ids),
        "comparable": summary.comparable,
        "mismatch_reasons": list(summary.mismatch_reasons),
        "candidate_structure_key": summary.candidate_structure_key_values[0]
        if summary.candidate_structure_key_values
        else report.metadata.get("candidate_structure_key"),
        "report_path": report.report_path,
    }


def _matrix_benchmark_export_comparison_export_overview(
    export: DeliberationCampaignMatrixBenchmarkExportComparisonExport,
) -> dict[str, Any]:
    return {
        "export_id": export.export_id,
        "created_at": export.created_at.isoformat(),
        "output_dir": export.output_dir,
        "comparison_id": export.comparison_id,
        "comparison_report_path": export.comparison_report_path,
        "format": export.format,
        "export_count": export.export_count,
        "export_ids": list(export.export_ids),
        "comparable": export.comparable,
        "mismatch_reasons": list(export.mismatch_reasons),
        "manifest_path": export.manifest_path,
        "content_path": export.content_path,
    }


def _matrix_benchmark_comparison_report_overview(
    report: DeliberationCampaignMatrixBenchmarkComparisonReport,
) -> dict[str, Any]:
    summary = report.summary
    return {
        "comparison_id": report.comparison_id,
        "created_at": report.created_at.isoformat(),
        "latest": report.latest,
        "requested_benchmark_ids": list(report.requested_benchmark_ids),
        "benchmark_count": summary.benchmark_count,
        "benchmark_ids": list(summary.benchmark_ids),
        "comparable": summary.comparable,
        "mismatch_reasons": list(summary.mismatch_reasons),
        "candidate_structure_key": summary.candidate_structure_key_values[0]
        if summary.candidate_structure_key_values
        else report.metadata.get("candidate_structure_key"),
        "report_path": report.report_path,
    }


def _matrix_benchmark_comparison_export_overview(
    export: DeliberationCampaignMatrixBenchmarkComparisonExport,
) -> dict[str, Any]:
    return {
        "export_id": export.export_id,
        "created_at": export.created_at.isoformat(),
        "output_dir": export.output_dir,
        "comparison_id": export.comparison_id,
        "comparison_report_path": export.comparison_report_path,
        "format": export.format,
        "benchmark_count": export.benchmark_count,
        "benchmark_ids": list(export.benchmark_ids),
        "comparable": export.comparable,
        "mismatch_reasons": list(export.mismatch_reasons),
        "manifest_path": export.manifest_path,
        "content_path": export.content_path,
    }


def render_deliberation_campaign_matrix_benchmark_markdown(
    benchmark_report: DeliberationCampaignMatrixBenchmarkBundle
    | DeliberationCampaignMatrixBenchmarkAudit
    | dict[str, Any],
) -> str:
    audit = (
        benchmark_report
        if isinstance(benchmark_report, DeliberationCampaignMatrixBenchmarkAudit)
        else build_deliberation_campaign_matrix_benchmark_audit(benchmark_report, include_markdown=False)
    )
    summary = audit.summary
    mismatch_reasons = ", ".join(summary.mismatch_reasons) if summary.mismatch_reasons else "none"
    lines = [
        "# Deliberation Campaign Matrix Benchmark Audit",
        f"- Benchmark ID: {audit.benchmark_id}",
        f"- Created At: {audit.created_at.isoformat()}",
        f"- Output Dir: {audit.output_dir}",
        f"- Benchmark Report Path: {audit.benchmark_report_path or 'n/a'}",
        f"- Baseline Campaign ID: {summary.baseline_campaign_id}",
        f"- Baseline Runtime: {summary.baseline_runtime}",
        f"- Baseline Engine: {summary.baseline_engine}",
        f"- Candidate Count: {summary.candidate_count}",
        f"- Comparable Candidates: {summary.comparable_count}",
        f"- Mismatched Candidates: {summary.mismatch_count}",
        f"- Mismatch Reasons: {mismatch_reasons}",
        f"- Best Candidate: #{summary.best_candidate_rank} {summary.best_candidate_label} ({summary.best_candidate_campaign_id})",
        f"- Worst Candidate: #{summary.worst_candidate_rank} {summary.worst_candidate_label} ({summary.worst_candidate_campaign_id})",
        "",
        "## Aggregate Metrics",
        f"- Quality Score Mean: {summary.quality_score_mean:.3f} (min {summary.quality_score_min:.3f}, max {summary.quality_score_max:.3f})",
        f"- Confidence Level Mean: {summary.confidence_level_mean:.3f} (min {summary.confidence_level_min:.3f}, max {summary.confidence_level_max:.3f})",
        f"- Runtimes: {', '.join(summary.runtime_values) if summary.runtime_values else 'n/a'}",
        f"- Engines: {', '.join(summary.engine_values) if summary.engine_values else 'n/a'}",
    ]
    if audit.entries:
        lines.extend(
            [
                "",
                "## Candidate Ranking",
                "| Rank | Candidate | Campaign ID | Runtime | Engine | Comparable | Score | Confidence | Comparison ID | Mismatch Reasons |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for entry in audit.entries:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(entry.rank),
                        entry.candidate_label,
                        entry.candidate_campaign_id,
                        entry.runtime,
                        entry.engine,
                        "yes" if entry.comparable else "no",
                        f"{entry.quality_score_mean:.3f}",
                        f"{entry.confidence_level_mean:.3f}",
                        entry.comparison_id,
                        ", ".join(entry.mismatch_reasons) if entry.mismatch_reasons else "none",
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _dashboard_counts_summary(counts: dict[str, int]) -> str:
    normalized_counts = { _normalize_text(key): int(value) for key, value in counts.items() if _normalize_text(key) }
    if not normalized_counts:
        return ""
    items = sorted(normalized_counts.items(), key=lambda item: (-item[1], item[0]))
    return ", ".join(f"{key}={value}" for key, value in items)


def _dashboard_sequence_summary(values: list[str]) -> str:
    normalized_values = [value for value in (_normalize_text(value) for value in values) if value]
    if not normalized_values:
        return ""
    return ", ".join(_sorted_unique_values(normalized_values))


def _dashboard_artifact_path(*, kind: str, report: Any) -> str | None:
    if kind == "campaign":
        return _normalize_text(getattr(report, "report_path", None)) or None
    if kind == "comparison":
        return _normalize_text(getattr(report, "report_path", None)) or None
    if kind == "export":
        return _normalize_text(getattr(report, "manifest_path", None)) or _normalize_text(getattr(report, "content_path", None)) or None
    if kind == "benchmark":
        return _normalize_text(getattr(report, "report_path", None)) or None
    if kind == "matrix_benchmark":
        return _normalize_text(getattr(report, "report_path", None)) or None
    if kind == "matrix_benchmark_export":
        return _normalize_text(getattr(report, "manifest_path", None)) or _normalize_text(
            getattr(report, "content_path", None)
        ) or None
    if kind == "matrix_benchmark_export_comparison":
        return _normalize_text(getattr(report, "report_path", None)) or None
    if kind == "matrix_benchmark_export_comparison_export":
        return _normalize_text(getattr(report, "manifest_path", None)) or _normalize_text(
            getattr(report, "content_path", None)
        ) or None
    if kind == "matrix_benchmark_comparison":
        return _normalize_text(getattr(report, "report_path", None)) or None
    if kind == "matrix_benchmark_comparison_export":
        return _normalize_text(getattr(report, "manifest_path", None)) or _normalize_text(
            getattr(report, "content_path", None)
        ) or None
    return None


def _dashboard_row_sort_value(row: DeliberationCampaignDashboardRow, sort_by: str) -> tuple[Any, ...]:
    normalized_sort_by = _normalize_text(sort_by) or "created_at"
    descending = normalized_sort_by.startswith("-")
    if descending:
        normalized_sort_by = normalized_sort_by[1:]

    value: Any
    if normalized_sort_by == "created_at":
        value = _campaign_created_at_sort_key(row.created_at)
    elif normalized_sort_by == "artifact_kind":
        value = _normalize_text(row.artifact_kind)
    elif normalized_sort_by == "artifact_id":
        value = _normalize_text(row.artifact_id)
    elif normalized_sort_by == "status":
        value = _normalize_text(row.status)
    elif normalized_sort_by == "comparable":
        value = 1 if row.comparable else 0
    elif normalized_sort_by == "quality_score_mean":
        value = float(row.quality_score_mean) if row.quality_score_mean is not None else float("-inf")
    elif normalized_sort_by == "confidence_level_mean":
        value = float(row.confidence_level_mean) if row.confidence_level_mean is not None else float("-inf")
    elif normalized_sort_by == "runtime_summary":
        value = _normalize_text(row.runtime_summary)
    elif normalized_sort_by == "engine_summary":
        value = _normalize_text(row.engine_summary)
    elif normalized_sort_by == "artifact_path":
        value = _normalize_text(row.artifact_path)
    else:
        value = _normalize_text(row.metadata.get(normalized_sort_by))

    if descending:
        return (value, _normalize_text(row.artifact_kind), _normalize_text(row.artifact_id))
    return (value, _normalize_text(row.artifact_kind), _normalize_text(row.artifact_id))


def _dashboard_kind_matches(kinds: set[str] | None, artifact_kind: str) -> bool:
    if not kinds:
        return True
    normalized_kind = _normalize_text(artifact_kind)
    return normalized_kind in kinds or (normalized_kind + "s") in kinds


def _normalize_dashboard_kind(kind: str) -> str:
    normalized = _normalize_text(kind)
    if normalized.endswith("s") and normalized[:-1] in {
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
    }:
        return normalized[:-1]
    return normalized


def _build_dashboard_row(
    *,
    artifact_kind: str,
    artifact_id: str,
    created_at: datetime,
    status: str | None,
    comparable: bool | None,
    quality_score_mean: float | None,
    confidence_level_mean: float | None,
    runtime_summary: str,
    engine_summary: str,
    artifact_path: str | None,
    metadata: dict[str, Any] | None = None,
) -> DeliberationCampaignDashboardRow:
    return DeliberationCampaignDashboardRow(
        artifact_kind=_normalize_text(artifact_kind),
        artifact_id=_normalize_text(artifact_id),
        created_at=created_at,
        status=_normalize_text(status) or None,
        comparable=comparable,
        quality_score_mean=quality_score_mean,
        confidence_level_mean=confidence_level_mean,
        runtime_summary=_normalize_text(runtime_summary),
        engine_summary=_normalize_text(engine_summary),
        artifact_path=_normalize_text(artifact_path) or None,
        metadata=dict(metadata or {}),
    )


def build_deliberation_campaign_dashboard(
    *,
    campaign_output_dir: str | Path | None = None,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
    benchmark_output_dir: str | Path | None = None,
    matrix_benchmark_output_dir: str | Path | None = None,
    matrix_benchmark_export_output_dir: str | Path | None = None,
    matrix_benchmark_export_comparison_output_dir: str | Path | None = None,
    matrix_benchmark_export_comparison_export_output_dir: str | Path | None = None,
    matrix_benchmark_comparison_output_dir: str | Path | None = None,
    matrix_benchmark_comparison_export_output_dir: str | Path | None = None,
    kinds: list[str] | None = None,
    limit: int | None = 20,
    sort_by: str = "created_at",
    campaign_status: DeliberationCampaignStatus | str | None = None,
    comparable_only: bool = False,
) -> DeliberationCampaignDashboard:
    requested_kinds = [_normalize_dashboard_kind(kind) for kind in (kinds or []) if _normalize_text(kind)]
    selected_kinds = {kind for kind in requested_kinds if kind}
    selected_status = _normalize_campaign_status(campaign_status) if campaign_status is not None else None

    campaigns = list_deliberation_campaign_reports(output_dir=campaign_output_dir, limit=None)
    comparisons = list_deliberation_campaign_comparison_reports(output_dir=comparison_output_dir, limit=None)
    exports = list_deliberation_campaign_comparison_exports(output_dir=export_output_dir, limit=None)
    benchmarks = list_deliberation_campaign_benchmarks(output_dir=benchmark_output_dir, limit=None)
    matrix_benchmarks = list_deliberation_campaign_matrix_benchmarks(output_dir=matrix_benchmark_output_dir, limit=None)
    matrix_benchmark_exports = list_deliberation_campaign_matrix_benchmark_exports(
        output_dir=matrix_benchmark_export_output_dir,
        limit=None,
    )
    matrix_benchmark_export_comparisons = list_deliberation_campaign_matrix_benchmark_export_comparison_reports(
        output_dir=matrix_benchmark_export_comparison_output_dir,
        limit=None,
    )
    matrix_benchmark_export_comparison_exports = (
        list_deliberation_campaign_matrix_benchmark_export_comparison_exports(
            output_dir=matrix_benchmark_export_comparison_export_output_dir,
            limit=None,
        )
    )
    matrix_benchmark_comparisons = list_deliberation_campaign_matrix_benchmark_comparison_reports(
        output_dir=matrix_benchmark_comparison_output_dir,
        limit=None,
    )
    matrix_benchmark_comparison_exports = list_deliberation_campaign_matrix_benchmark_comparison_exports(
        output_dir=matrix_benchmark_comparison_export_output_dir,
        limit=None,
    )
    comparison_lookup = {report.comparison_id: report for report in comparisons}

    rows: list[DeliberationCampaignDashboardRow] = []

    for report in campaigns:
        row = _build_dashboard_row(
            artifact_kind="campaign",
            artifact_id=report.campaign_id,
            created_at=report.created_at,
            status=report.status.value,
            comparable=True,
            quality_score_mean=report.summary.quality_score_mean,
            confidence_level_mean=report.summary.confidence_level_mean,
            runtime_summary=_dashboard_counts_summary(dict(report.summary.runtime_counts)),
            engine_summary=_dashboard_counts_summary(dict(report.summary.engine_counts)),
            artifact_path=_dashboard_artifact_path(kind="campaign", report=report),
            metadata={
                "topic": report.topic,
                "objective": report.objective,
                "mode": report.mode.value,
                "runtime_requested": report.runtime_requested,
                "engine_requested": report.engine_requested,
                "sample_count_requested": report.sample_count_requested,
                "sample_count_completed": report.summary.sample_count_completed,
                "sample_count_failed": report.summary.sample_count_failed,
                "fallback_guard_applied": report.fallback_guard_applied,
                "comparison_key": report.metadata.get("comparison_key"),
            },
        )
        rows.append(row)

    for report in comparisons:
        summary = report.summary
        runtime_summary = _dashboard_sequence_summary(list(summary.runtime_values))
        engine_summary = _dashboard_sequence_summary(list(summary.engine_values))
        row = _build_dashboard_row(
            artifact_kind="comparison",
            artifact_id=report.comparison_id,
            created_at=report.created_at,
            status="comparable" if summary.comparable else "mismatch",
            comparable=summary.comparable,
            quality_score_mean=summary.quality_score_mean,
            confidence_level_mean=summary.confidence_level_mean,
            runtime_summary=runtime_summary,
            engine_summary=engine_summary,
            artifact_path=_dashboard_artifact_path(kind="comparison", report=report),
            metadata={
                "requested_campaign_ids": list(report.requested_campaign_ids),
                "latest": report.latest,
                "campaign_ids": list(summary.campaign_ids),
                "mismatch_reasons": list(summary.mismatch_reasons),
                "comparison_key": summary.comparison_key_values[0] if summary.comparison_key_values else report.metadata.get("comparison_key"),
            },
        )
        rows.append(row)

    for export in exports:
        comparison_report = comparison_lookup.get(export.comparison_id)
        summary = comparison_report.summary if comparison_report is not None else None
        row = _build_dashboard_row(
            artifact_kind="export",
            artifact_id=export.export_id,
            created_at=export.created_at,
            status="comparable" if export.comparable else "mismatch",
            comparable=export.comparable,
            quality_score_mean=summary.quality_score_mean if summary is not None else None,
            confidence_level_mean=summary.confidence_level_mean if summary is not None else None,
            runtime_summary=_dashboard_sequence_summary(list(summary.runtime_values)) if summary is not None else "",
            engine_summary=_dashboard_sequence_summary(list(summary.engine_values)) if summary is not None else "",
            artifact_path=_dashboard_artifact_path(kind="export", report=export),
            metadata={
                "comparison_id": export.comparison_id,
                "comparison_report_path": export.comparison_report_path,
                "format": export.format,
                "campaign_ids": list(export.campaign_ids),
                "mismatch_reasons": list(export.mismatch_reasons),
            },
        )
        rows.append(row)

    for benchmark in benchmarks:
        comparison_report = benchmark.comparison_bundle.comparison_report
        summary = comparison_report.summary
        metadata = dict(benchmark.metadata)
        runtime_summary = _dashboard_sequence_summary(
            [metadata.get("baseline_runtime", ""), metadata.get("candidate_runtime", "")]
        )
        engine_summary = _dashboard_sequence_summary(
            [metadata.get("baseline_engine_preference", ""), metadata.get("candidate_engine_preference", "")]
        )
        row = _build_dashboard_row(
            artifact_kind="benchmark",
            artifact_id=benchmark.benchmark_id,
            created_at=benchmark.created_at,
            status="comparable" if summary.comparable else "mismatch",
            comparable=summary.comparable,
            quality_score_mean=summary.quality_score_mean,
            confidence_level_mean=summary.confidence_level_mean,
            runtime_summary=runtime_summary,
            engine_summary=engine_summary,
            artifact_path=_dashboard_artifact_path(kind="benchmark", report=benchmark),
            metadata={
                "baseline_campaign_id": benchmark.baseline_campaign.campaign_id,
                "candidate_campaign_id": benchmark.candidate_campaign.campaign_id,
                "comparison_id": comparison_report.comparison_id,
                "export_id": benchmark.comparison_bundle.export.export_id,
                "format": benchmark.comparison_bundle.export.format,
                "comparison_report_path": comparison_report.report_path,
                "export_manifest_path": benchmark.comparison_bundle.export.manifest_path,
                "export_content_path": benchmark.comparison_bundle.export.content_path,
            },
        )
        rows.append(row)

    for matrix_benchmark in matrix_benchmarks:
        row = _build_dashboard_row(
            artifact_kind="matrix_benchmark",
            artifact_id=matrix_benchmark.benchmark_id,
            created_at=matrix_benchmark.created_at,
            status="comparable" if matrix_benchmark.summary.mismatch_count == 0 else "mismatch",
            comparable=matrix_benchmark.summary.mismatch_count == 0,
            quality_score_mean=matrix_benchmark.summary.quality_score_mean,
            confidence_level_mean=matrix_benchmark.summary.confidence_level_mean,
            runtime_summary=_dashboard_sequence_summary(list(matrix_benchmark.summary.runtime_values)),
            engine_summary=_dashboard_sequence_summary(list(matrix_benchmark.summary.engine_values)),
            artifact_path=_dashboard_artifact_path(kind="matrix_benchmark", report=matrix_benchmark),
            metadata={
                "baseline_campaign_id": matrix_benchmark.baseline_campaign.campaign_id,
                "candidate_count": matrix_benchmark.summary.candidate_count,
                "candidate_campaign_ids": list(matrix_benchmark.summary.candidate_campaign_ids),
                "candidate_labels": list(matrix_benchmark.summary.candidate_labels),
                "comparison_ids": list(matrix_benchmark.summary.comparison_ids),
                "mismatch_count": matrix_benchmark.summary.mismatch_count,
                "comparable_count": matrix_benchmark.summary.comparable_count,
            },
        )
        rows.append(row)

    for export in matrix_benchmark_exports:
        export_metadata = getattr(export, "metadata", {})
        if not isinstance(export_metadata, dict):
            export_metadata = {}
        row = _build_dashboard_row(
            artifact_kind="matrix_benchmark_export",
            artifact_id=export.export_id,
            created_at=export.created_at,
            status="comparable" if export.mismatch_count == 0 else "mismatch",
            comparable=export.mismatch_count == 0,
            quality_score_mean=export_metadata.get("quality_score_mean"),
            confidence_level_mean=export_metadata.get("confidence_level_mean"),
            runtime_summary="",
            engine_summary="",
            artifact_path=_dashboard_artifact_path(kind="matrix_benchmark_export", report=export),
            metadata={
                "benchmark_id": export.benchmark_id,
                "benchmark_report_path": export.benchmark_report_path,
                "format": export.format,
                "candidate_count": export.candidate_count,
                "comparable_count": export.comparable_count,
                "mismatch_count": export.mismatch_count,
                "best_candidate_label": export.best_candidate_label,
                "worst_candidate_label": export.worst_candidate_label,
            },
        )
        rows.append(row)

    for report in matrix_benchmark_export_comparisons:
        summary = report.summary
        row = _build_dashboard_row(
            artifact_kind="matrix_benchmark_export_comparison",
            artifact_id=report.comparison_id,
            created_at=report.created_at,
            status="comparable" if summary.comparable else "mismatch",
            comparable=summary.comparable,
            quality_score_mean=summary.quality_score_mean,
            confidence_level_mean=summary.confidence_level_mean,
            runtime_summary=_dashboard_sequence_summary(list(summary.baseline_runtime_values)),
            engine_summary=_dashboard_sequence_summary(list(summary.baseline_engine_values)),
            artifact_path=_dashboard_artifact_path(kind="matrix_benchmark_export_comparison", report=report),
            metadata={
                "requested_export_ids": list(report.requested_export_ids),
                "latest": report.latest,
                "export_ids": list(summary.export_ids),
                "benchmark_ids": list(summary.benchmark_ids),
                "format_values": list(summary.format_values),
                "mismatch_reasons": list(summary.mismatch_reasons),
                "candidate_structure_key": summary.candidate_structure_key_values[0]
                if summary.candidate_structure_key_values
                else report.metadata.get("candidate_structure_key"),
            },
        )
        rows.append(row)

    matrix_benchmark_export_comparison_lookup = {
        report.comparison_id: report for report in matrix_benchmark_export_comparisons
    }

    for export in matrix_benchmark_export_comparison_exports:
        comparison_report = matrix_benchmark_export_comparison_lookup.get(export.comparison_id)
        summary = comparison_report.summary if comparison_report is not None else None
        row = _build_dashboard_row(
            artifact_kind="matrix_benchmark_export_comparison_export",
            artifact_id=export.export_id,
            created_at=export.created_at,
            status="comparable" if export.comparable else "mismatch",
            comparable=export.comparable,
            quality_score_mean=summary.quality_score_mean if summary is not None else None,
            confidence_level_mean=summary.confidence_level_mean if summary is not None else None,
            runtime_summary=_dashboard_sequence_summary(list(summary.baseline_runtime_values)) if summary is not None else "",
            engine_summary=_dashboard_sequence_summary(list(summary.baseline_engine_values)) if summary is not None else "",
            artifact_path=_dashboard_artifact_path(kind="matrix_benchmark_export_comparison_export", report=export),
            metadata={
                "comparison_id": export.comparison_id,
                "comparison_report_path": export.comparison_report_path,
                "format": export.format,
                "export_ids": list(export.export_ids),
                "mismatch_reasons": list(export.mismatch_reasons),
            },
        )
        rows.append(row)

    for report in matrix_benchmark_comparisons:
        summary = report.summary
        row = _build_dashboard_row(
            artifact_kind="matrix_benchmark_comparison",
            artifact_id=report.comparison_id,
            created_at=report.created_at,
            status="comparable" if summary.comparable else "mismatch",
            comparable=summary.comparable,
            quality_score_mean=summary.quality_score_mean,
            confidence_level_mean=summary.confidence_level_mean,
            runtime_summary=_dashboard_sequence_summary(list(summary.runtime_values)),
            engine_summary=_dashboard_sequence_summary(list(summary.engine_values)),
            artifact_path=_dashboard_artifact_path(kind="matrix_benchmark_comparison", report=report),
            metadata={
                "requested_benchmark_ids": list(report.requested_benchmark_ids),
                "latest": report.latest,
                "benchmark_ids": list(summary.benchmark_ids),
                "mismatch_reasons": list(summary.mismatch_reasons),
                "candidate_structure_key": summary.candidate_structure_key_values[0]
                if summary.candidate_structure_key_values
                else report.metadata.get("candidate_structure_key"),
            },
        )
        rows.append(row)

    matrix_benchmark_comparison_lookup = {report.comparison_id: report for report in matrix_benchmark_comparisons}

    for export in matrix_benchmark_comparison_exports:
        comparison_report = matrix_benchmark_comparison_lookup.get(export.comparison_id)
        summary = comparison_report.summary if comparison_report is not None else None
        row = _build_dashboard_row(
            artifact_kind="matrix_benchmark_comparison_export",
            artifact_id=export.export_id,
            created_at=export.created_at,
            status="comparable" if export.comparable else "mismatch",
            comparable=export.comparable,
            quality_score_mean=summary.quality_score_mean if summary is not None else None,
            confidence_level_mean=summary.confidence_level_mean if summary is not None else None,
            runtime_summary=_dashboard_sequence_summary(list(summary.runtime_values)) if summary is not None else "",
            engine_summary=_dashboard_sequence_summary(list(summary.engine_values)) if summary is not None else "",
            artifact_path=_dashboard_artifact_path(kind="matrix_benchmark_comparison_export", report=export),
            metadata={
                "comparison_id": export.comparison_id,
                "comparison_report_path": export.comparison_report_path,
                "format": export.format,
                "benchmark_ids": list(export.benchmark_ids),
                "mismatch_reasons": list(export.mismatch_reasons),
            },
        )
        rows.append(row)

    if selected_kinds:
        rows = [row for row in rows if _dashboard_kind_matches(selected_kinds, row.artifact_kind)]

    if selected_status is not None:
        rows = [row for row in rows if row.artifact_kind != "campaign" or _normalize_campaign_status(row.status or "") == selected_status]

    if comparable_only:
        rows = [row for row in rows if row.comparable]

    rows.sort(key=lambda row: _dashboard_row_sort_value(row, sort_by), reverse=True)

    if limit is not None:
        rows = rows[: max(0, int(limit))]

    counts = Counter(row.artifact_kind for row in rows)
    return DeliberationCampaignDashboard(
        kinds=sorted(selected_kinds) if selected_kinds else [],
        limit=limit,
        sort_by=sort_by,
        campaign_status=selected_status if selected_status is not None else campaign_status,
        comparable_only=comparable_only,
        rows=rows,
        counts=dict(counts),
        metadata={
            "campaign_count": len(campaigns),
            "comparison_count": len(comparisons),
            "export_count": len(exports),
            "benchmark_count": len(benchmarks),
            "matrix_benchmark_count": len(matrix_benchmarks),
            "matrix_benchmark_export_count": len(matrix_benchmark_exports),
            "matrix_benchmark_export_comparison_count": len(matrix_benchmark_export_comparisons),
            "matrix_benchmark_export_comparison_export_count": len(
                matrix_benchmark_export_comparison_exports
            ),
            "matrix_benchmark_comparison_count": len(matrix_benchmark_comparisons),
            "matrix_benchmark_comparison_export_count": len(matrix_benchmark_comparison_exports),
            "row_count": len(rows),
            "available_kinds": [
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
            ],
            "selected_kinds": sorted(selected_kinds) if selected_kinds else [],
            "selected_status": selected_status.value if selected_status is not None else None,
            "comparable_only": comparable_only,
            "sort_by": sort_by,
            "source_counts": {
                "campaigns": len(campaigns),
                "comparisons": len(comparisons),
                "exports": len(exports),
                "benchmarks": len(benchmarks),
                "matrix_benchmarks": len(matrix_benchmarks),
                "matrix_benchmark_exports": len(matrix_benchmark_exports),
                "matrix_benchmark_export_comparisons": len(matrix_benchmark_export_comparisons),
                "matrix_benchmark_export_comparison_exports": len(
                    matrix_benchmark_export_comparison_exports
                ),
                "matrix_benchmark_comparisons": len(matrix_benchmark_comparisons),
                "matrix_benchmark_comparison_exports": len(matrix_benchmark_comparison_exports),
            },
        },
    )


def build_deliberation_campaign_artifact_index(
    *,
    campaign_output_dir: str | Path | None = None,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
    benchmark_output_dir: str | Path | None = None,
    matrix_benchmark_output_dir: str | Path | None = None,
    matrix_benchmark_export_output_dir: str | Path | None = None,
    matrix_benchmark_export_comparison_output_dir: str | Path | None = None,
    matrix_benchmark_export_comparison_export_output_dir: str | Path | None = None,
    matrix_benchmark_comparison_output_dir: str | Path | None = None,
    matrix_benchmark_comparison_export_output_dir: str | Path | None = None,
    limit: int = 20,
) -> DeliberationCampaignArtifactIndex:
    campaigns = list_deliberation_campaign_reports(output_dir=campaign_output_dir, limit=limit)
    comparisons = list_deliberation_campaign_comparison_reports(output_dir=comparison_output_dir, limit=limit)
    exports = list_deliberation_campaign_comparison_exports(output_dir=export_output_dir, limit=limit)
    benchmarks = list_deliberation_campaign_benchmarks(output_dir=benchmark_output_dir, limit=limit)
    matrix_benchmarks = list_deliberation_campaign_matrix_benchmarks(
        output_dir=matrix_benchmark_output_dir,
        limit=limit,
    )
    matrix_benchmark_exports = list_deliberation_campaign_matrix_benchmark_exports(
        output_dir=matrix_benchmark_export_output_dir,
        limit=limit,
    )
    matrix_benchmark_export_comparisons = list_deliberation_campaign_matrix_benchmark_export_comparison_reports(
        output_dir=matrix_benchmark_export_comparison_output_dir,
        limit=limit,
    )
    matrix_benchmark_export_comparison_exports = (
        list_deliberation_campaign_matrix_benchmark_export_comparison_exports(
            output_dir=matrix_benchmark_export_comparison_export_output_dir,
            limit=limit,
        )
    )
    matrix_benchmark_comparisons = list_deliberation_campaign_matrix_benchmark_comparison_reports(
        output_dir=matrix_benchmark_comparison_output_dir,
        limit=limit,
    )
    matrix_benchmark_comparison_exports = list_deliberation_campaign_matrix_benchmark_comparison_exports(
        output_dir=matrix_benchmark_comparison_export_output_dir,
        limit=limit,
    )

    campaign_dir = Path(campaign_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR)
    comparison_dir = Path(comparison_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR)
    export_dir = Path(export_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR)
    benchmark_dir = Path(benchmark_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR)
    matrix_benchmark_dir = Path(
        matrix_benchmark_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR
    )
    matrix_benchmark_export_dir = Path(
        matrix_benchmark_export_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR
    )
    matrix_benchmark_export_comparison_dir = Path(
        matrix_benchmark_export_comparison_output_dir
        or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR
    )
    matrix_benchmark_export_comparison_export_dir = Path(
        matrix_benchmark_export_comparison_export_output_dir
        or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR
    )
    matrix_benchmark_comparison_dir = Path(
        matrix_benchmark_comparison_output_dir
        or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR
    )
    matrix_benchmark_comparison_export_dir = Path(
        matrix_benchmark_comparison_export_output_dir
        or DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR
    )

    return DeliberationCampaignArtifactIndex(
        output_dirs={
            "campaigns": str(campaign_dir),
            "comparisons": str(comparison_dir),
            "exports": str(export_dir),
            "benchmarks": str(benchmark_dir),
            "matrix_benchmarks": str(matrix_benchmark_dir),
            "matrix_benchmark_exports": str(matrix_benchmark_export_dir),
            "matrix_benchmark_export_comparisons": str(matrix_benchmark_export_comparison_dir),
            "matrix_benchmark_export_comparison_exports": str(
                matrix_benchmark_export_comparison_export_dir
            ),
            "matrix_benchmark_comparisons": str(matrix_benchmark_comparison_dir),
            "matrix_benchmark_comparison_exports": str(matrix_benchmark_comparison_export_dir),
        },
        counts={
            "campaigns": len(campaigns),
            "comparisons": len(comparisons),
            "exports": len(exports),
            "benchmarks": len(benchmarks),
            "matrix_benchmarks": len(matrix_benchmarks),
            "matrix_benchmark_exports": len(matrix_benchmark_exports),
            "matrix_benchmark_export_comparisons": len(matrix_benchmark_export_comparisons),
            "matrix_benchmark_export_comparison_exports": len(matrix_benchmark_export_comparison_exports),
            "matrix_benchmark_comparisons": len(matrix_benchmark_comparisons),
            "matrix_benchmark_comparison_exports": len(matrix_benchmark_comparison_exports),
        },
        campaigns=[_campaign_report_overview(report) for report in campaigns],
        comparisons=[_comparison_report_overview(report) for report in comparisons],
        exports=[_comparison_export_overview(export) for export in exports],
        benchmarks=[_benchmark_report_overview(benchmark) for benchmark in benchmarks],
        matrix_benchmarks=[_matrix_benchmark_report_overview(benchmark) for benchmark in matrix_benchmarks],
        matrix_benchmark_exports=[
            _matrix_benchmark_export_overview(export)
            for export in matrix_benchmark_exports
        ],
        matrix_benchmark_export_comparisons=[
            _matrix_benchmark_export_comparison_report_overview(report)
            for report in matrix_benchmark_export_comparisons
        ],
        matrix_benchmark_export_comparison_exports=[
            _matrix_benchmark_export_comparison_export_overview(export)
            for export in matrix_benchmark_export_comparison_exports
        ],
        matrix_benchmark_comparisons=[
            _matrix_benchmark_comparison_report_overview(report)
            for report in matrix_benchmark_comparisons
        ],
        matrix_benchmark_comparison_exports=[
            _matrix_benchmark_comparison_export_overview(export)
            for export in matrix_benchmark_comparison_exports
        ],
        metadata={
            "limit": limit,
            "artifact_count": (
                len(campaigns)
                + len(comparisons)
                + len(exports)
                + len(benchmarks)
                + len(matrix_benchmarks)
                + len(matrix_benchmark_exports)
                + len(matrix_benchmark_export_comparisons)
                + len(matrix_benchmark_export_comparison_exports)
                + len(matrix_benchmark_comparisons)
                + len(matrix_benchmark_comparison_exports)
            ),
        },
    )


def _comparison_export_dir(export_id: str, *, output_dir: str | Path | None = None) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR)
    return base_dir / export_id


def _comparison_export_manifest_path(export_id: str, *, output_dir: str | Path | None = None) -> Path:
    return _comparison_export_dir(export_id, output_dir=output_dir) / "manifest.json"


def _comparison_export_content_path(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> Path:
    extension = ".md" if str(format).strip().lower() == "markdown" else ".json"
    return _comparison_export_dir(export_id, output_dir=output_dir) / f"content{extension}"


def build_deliberation_campaign_comparison_export(
    comparison_report: DeliberationCampaignComparisonReport | DeliberationCampaignComparisonAudit | dict[str, Any],
    *,
    format: str = "markdown",
    include_content: bool = True,
) -> DeliberationCampaignComparisonExport:
    normalized_format = str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        raise ValueError("format must be one of: markdown, json")

    audit = (
        comparison_report
        if isinstance(comparison_report, DeliberationCampaignComparisonAudit)
        else build_deliberation_campaign_comparison_audit(comparison_report, include_markdown=normalized_format == "markdown")
    )
    content = (
        render_deliberation_campaign_comparison_markdown(audit)
        if normalized_format == "markdown"
        else json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True)
    )
    export = DeliberationCampaignComparisonExport(
        output_dir=audit.output_dir,
        comparison_id=audit.comparison_id,
        comparison_report_path=audit.report_path,
        format=normalized_format,
        campaign_count=audit.campaign_count,
        campaign_ids=list(audit.campaign_ids),
        comparable=audit.comparable,
        mismatch_reasons=list(audit.mismatch_reasons),
        content=content if include_content else None,
        metadata={
            **audit.metadata,
            "comparison_id": audit.comparison_id,
            "comparison_report_path": audit.report_path,
            "content_format": normalized_format,
            "content_kind": "markdown" if normalized_format == "markdown" else "json",
        },
    )
    return export


def materialize_deliberation_campaign_comparison_export(
    comparison_report: DeliberationCampaignComparisonReport | DeliberationCampaignComparisonAudit | dict[str, Any],
    *,
    format: str = "markdown",
    output_dir: str | Path | None = None,
    export_id: str | None = None,
) -> DeliberationCampaignComparisonExport:
    export = build_deliberation_campaign_comparison_export(comparison_report, format=format, include_content=True)
    if export_id:
        export.export_id = _normalize_text(export_id) or export.export_id
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR)
    export.output_dir = str(base_dir)
    export_dir = _comparison_export_dir(export.export_id, output_dir=base_dir)
    manifest_path = export_dir / "manifest.json"
    content_path = _comparison_export_content_path(export.export_id, output_dir=base_dir, format=export.format)
    export_dir.mkdir(parents=True, exist_ok=True)
    export.manifest_path = str(manifest_path)
    export.content_path = str(content_path)
    export.metadata["manifest_path"] = str(manifest_path)
    export.metadata["content_path"] = str(content_path)
    export.metadata["persisted"] = True
    manifest_path.write_text(
        json.dumps(export.model_dump(mode="json", exclude={"content"}), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if export.content is not None:
        content_path.write_text(export.content, encoding="utf-8")
    return export


def load_deliberation_campaign_comparison_export(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
    include_content: bool = True,
) -> DeliberationCampaignComparisonExport:
    manifest_path = _comparison_export_manifest_path(export_id, output_dir=output_dir)
    export = DeliberationCampaignComparisonExport.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if include_content and export.content_path:
        content_path = Path(export.content_path)
        if content_path.is_file():
            export.content = content_path.read_text(encoding="utf-8")
    return export


def list_deliberation_campaign_comparison_exports(
    *,
    output_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[DeliberationCampaignComparisonExport]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR)
    if not base_dir.exists():
        return []

    exports: list[DeliberationCampaignComparisonExport] = []
    for export_dir in base_dir.iterdir():
        if not export_dir.is_dir():
            continue
        manifest_path = export_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            export = DeliberationCampaignComparisonExport.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, json.JSONDecodeError):
            continue
        exports.append(export)

    exports.sort(
        key=lambda export: (
            _campaign_created_at_sort_key(export.created_at),
            export.export_id,
        ),
        reverse=True,
    )
    if limit is None:
        return exports
    return exports[: max(0, int(limit))]


def render_deliberation_campaign_comparison_markdown(
    comparison_report: DeliberationCampaignComparisonReport | DeliberationCampaignComparisonAudit | dict[str, Any],
) -> str:
    audit = (
        comparison_report
        if isinstance(comparison_report, DeliberationCampaignComparisonAudit)
        else build_deliberation_campaign_comparison_audit(comparison_report, include_markdown=False)
    )
    requested_campaign_ids = ", ".join(audit.requested_campaign_ids) if audit.requested_campaign_ids else "n/a"
    campaign_ids = ", ".join(audit.campaign_ids) if audit.campaign_ids else "n/a"
    mismatch_reasons = ", ".join(audit.mismatch_reasons) if audit.mismatch_reasons else "none"
    summary = audit.summary
    lines = [
        "# Deliberation Campaign Comparison",
        f"- Comparison ID: {audit.comparison_id}",
        f"- Created At: {audit.created_at.isoformat()}",
        f"- Output Dir: {audit.output_dir}",
        f"- Report Path: {audit.report_path or 'n/a'}",
        f"- Requested Campaign IDs: {requested_campaign_ids}",
        f"- Latest: {audit.latest if audit.latest is not None else 'n/a'}",
        f"- Comparable: {'yes' if audit.comparable else 'no'}",
        f"- Mismatch Reasons: {mismatch_reasons}",
        f"- Campaign Count: {audit.campaign_count}",
        f"- Campaign IDs: {campaign_ids}",
        "",
        "## Aggregate Metrics",
        f"- Quality Score Mean: {summary.quality_score_mean:.3f} (min {summary.quality_score_min:.3f}, max {summary.quality_score_max:.3f})",
        f"- Confidence Level Mean: {summary.confidence_level_mean:.3f} (min {summary.confidence_level_min:.3f}, max {summary.confidence_level_max:.3f})",
        f"- Samples Requested: {summary.sample_count_requested_total}",
        f"- Samples Completed: {summary.sample_count_completed_total}",
        f"- Samples Failed: {summary.sample_count_failed_total}",
    ]
    if audit.entries:
        lines.extend(
            [
                "",
                "## Entries",
                "| Campaign ID | Status | Topic | Runtime | Engine | Samples | Stability | Fallback | Score | Confidence |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for entry in audit.entries:
            lines.append(
                "| "
                + " | ".join(
                    [
                        entry.campaign_id,
                        entry.status.value,
                        entry.topic,
                        entry.runtime_requested,
                        entry.engine_requested,
                        f"{entry.sample_count_completed}/{entry.sample_count_requested}",
                        str(entry.stability_runs),
                        str(entry.fallback_count),
                        f"{entry.quality_score_mean:.3f}",
                        f"{entry.confidence_level_mean:.3f}",
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def list_deliberation_campaign_reports(
    *,
    output_dir: str | Path | None = None,
    status: DeliberationCampaignStatus | str | None = None,
    limit: int | None = None,
) -> list[DeliberationCampaignReport]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR)
    if not base_dir.exists():
        return []

    selected_status = _normalize_campaign_status(status) if status is not None else None
    reports: list[DeliberationCampaignReport] = []
    for campaign_dir in base_dir.iterdir():
        if not campaign_dir.is_dir():
            continue
        report_path = campaign_dir / "report.json"
        if not report_path.is_file():
            continue
        try:
            report = DeliberationCampaignReport.model_validate_json(report_path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, json.JSONDecodeError):
            continue
        if selected_status is not None and report.status != selected_status:
            continue
        reports.append(report)

    reports.sort(key=lambda report: (_campaign_created_at_sort_key(report.created_at), report.campaign_id), reverse=True)
    if limit is None:
        return reports
    return reports[: max(0, int(limit))]


def _selected_deliberation_campaign_reports(
    *,
    campaign_ids: list[str] | None,
    latest: int | None,
    output_dir: str | Path | None,
) -> list[DeliberationCampaignReport]:
    selected_reports: list[DeliberationCampaignReport] = []
    seen_campaign_ids: set[str] = set()

    for campaign_id in campaign_ids or []:
        normalized_campaign_id = _normalize_text(campaign_id)
        if not normalized_campaign_id or normalized_campaign_id in seen_campaign_ids:
            continue
        selected_reports.append(load_deliberation_campaign_report(normalized_campaign_id, output_dir=output_dir))
        seen_campaign_ids.add(normalized_campaign_id)

    if latest is not None:
        latest_count = int(latest)
        if latest_count <= 0:
            raise ValueError("latest must be a positive integer when provided")
        for report in list_deliberation_campaign_reports(output_dir=output_dir, limit=latest_count):
            if report.campaign_id in seen_campaign_ids:
                continue
            selected_reports.append(report)
            seen_campaign_ids.add(report.campaign_id)

    if not selected_reports:
        raise ValueError("At least one campaign_id or latest value must be provided")

    return selected_reports


def _selected_deliberation_campaign_matrix_benchmarks(
    *,
    benchmark_ids: list[str] | None,
    latest: int | None,
    output_dir: str | Path | None,
) -> list[DeliberationCampaignMatrixBenchmarkBundle]:
    selected_benchmarks: list[DeliberationCampaignMatrixBenchmarkBundle] = []
    seen_benchmark_ids: set[str] = set()

    for benchmark_id in benchmark_ids or []:
        normalized_benchmark_id = _normalize_text(benchmark_id)
        if not normalized_benchmark_id or normalized_benchmark_id in seen_benchmark_ids:
            continue
        selected_benchmarks.append(
            load_deliberation_campaign_matrix_benchmark(normalized_benchmark_id, output_dir=output_dir)
        )
        seen_benchmark_ids.add(normalized_benchmark_id)

    if latest is not None:
        latest_count = int(latest)
        if latest_count <= 0:
            raise ValueError("latest must be a positive integer when provided")
        for benchmark in list_deliberation_campaign_matrix_benchmarks(output_dir=output_dir, limit=latest_count):
            if benchmark.benchmark_id in seen_benchmark_ids:
                continue
            selected_benchmarks.append(benchmark)
            seen_benchmark_ids.add(benchmark.benchmark_id)

    if not selected_benchmarks:
        raise ValueError("At least one benchmark_id or latest value must be provided")

    return selected_benchmarks


def _selected_deliberation_campaign_matrix_benchmark_exports(
    *,
    export_ids: list[str] | None,
    latest: int | None,
    output_dir: str | Path | None,
) -> list[DeliberationCampaignMatrixBenchmarkExport]:
    selected_exports: list[DeliberationCampaignMatrixBenchmarkExport] = []
    seen_export_ids: set[str] = set()

    for export_id in export_ids or []:
        normalized_export_id = _normalize_text(export_id)
        if not normalized_export_id or normalized_export_id in seen_export_ids:
            continue
        selected_exports.append(
            load_deliberation_campaign_matrix_benchmark_export(normalized_export_id, output_dir=output_dir)
        )
        seen_export_ids.add(normalized_export_id)

    if latest is not None:
        latest_count = int(latest)
        if latest_count <= 0:
            raise ValueError("latest must be a positive integer when provided")
        for export in list_deliberation_campaign_matrix_benchmark_exports(output_dir=output_dir, limit=latest_count):
            if export.export_id in seen_export_ids:
                continue
            selected_exports.append(export)
            seen_export_ids.add(export.export_id)

    if not selected_exports:
        raise ValueError("At least one export_id or latest value must be provided")

    return selected_exports


def _matrix_benchmark_export_candidate_structure_key(
    export: DeliberationCampaignMatrixBenchmarkExport,
) -> str:
    labels = [_normalize_text(label) for label in export.candidate_labels if _normalize_text(label)]
    campaign_ids = [
        _normalize_text(candidate_campaign_id)
        for candidate_campaign_id in export.candidate_campaign_ids
        if _normalize_text(candidate_campaign_id)
    ]
    structure_parts: list[str] = []
    for index in range(max(len(labels), len(campaign_ids))):
        label = labels[index] if index < len(labels) else ""
        candidate_campaign_id = campaign_ids[index] if index < len(campaign_ids) else ""
        structure_parts.append(f"{index + 1}:{label}:{candidate_campaign_id}")
    return "|".join(structure_parts) or f"candidate_count={int(export.candidate_count or 0)}"


def _comparison_entry_from_report(report: DeliberationCampaignReport) -> DeliberationCampaignComparisonEntry:
    comparison_key = _report_comparison_key(report)
    return DeliberationCampaignComparisonEntry(
        campaign_id=report.campaign_id,
        created_at=report.created_at,
        status=report.status,
        topic=_normalize_text(report.topic),
        mode=report.mode.value,
        runtime_requested=_normalize_text(report.runtime_requested),
        engine_requested=_normalize_text(report.engine_requested),
        sample_count_requested=report.sample_count_requested,
        stability_runs=report.stability_runs,
        comparison_key=comparison_key,
        sample_count_completed=report.summary.sample_count_completed,
        sample_count_failed=report.summary.sample_count_failed,
        fallback_count=report.summary.fallback_count,
        runtime_counts=dict(report.summary.runtime_counts),
        engine_counts=dict(report.summary.engine_counts),
        quality_score_mean=report.summary.quality_score_mean,
        quality_score_min=report.summary.quality_score_min,
        quality_score_max=report.summary.quality_score_max,
        confidence_level_mean=report.summary.confidence_level_mean,
        confidence_level_min=report.summary.confidence_level_min,
        confidence_level_max=report.summary.confidence_level_max,
        fallback_guard_applied=report.fallback_guard_applied,
        fallback_guard_reason=report.fallback_guard_reason,
        report_path=report.report_path,
    )


def _comparison_summary_from_entries(
    entries: list[DeliberationCampaignComparisonEntry],
    reports: list[DeliberationCampaignReport],
) -> DeliberationCampaignComparisonSummary:
    campaign_ids = [entry.campaign_id for entry in entries]
    status_counts = Counter(entry.status.value for entry in entries)
    topic_values = _sorted_unique_values(entry.topic for entry in entries)
    mode_values = _sorted_unique_values(entry.mode for entry in entries)
    runtime_values = _sorted_unique_values(entry.runtime_requested for entry in entries)
    engine_values = _sorted_unique_values(entry.engine_requested for entry in entries)
    sample_count_values = _sorted_unique_values((entry.sample_count_requested for entry in entries), key=int)
    stability_runs_values = _sorted_unique_values((entry.stability_runs for entry in entries), key=int)
    comparison_key_values = _sorted_unique_values(entry.comparison_key for entry in entries)
    mismatch_reasons: list[str] = []

    if len(topic_values) > 1:
        mismatch_reasons.append("topic_mismatch")
    if len(mode_values) > 1:
        mismatch_reasons.append("mode_mismatch")
    if len(runtime_values) > 1:
        mismatch_reasons.append("runtime_mismatch")
    if len(engine_values) > 1:
        mismatch_reasons.append("engine_mismatch")
    if len(sample_count_values) > 1:
        mismatch_reasons.append("sample_count_mismatch")
    if len(stability_runs_values) > 1:
        mismatch_reasons.append("stability_runs_mismatch")
    if len(comparison_key_values) > 1:
        mismatch_reasons.append("comparison_key_mismatch")

    quality_score_means = [entry.quality_score_mean for entry in entries]
    confidence_level_means = [entry.confidence_level_mean for entry in entries]
    sample_count_requested_total = sum(entry.sample_count_requested for entry in entries)
    sample_count_completed_total = sum(entry.sample_count_completed for entry in entries)
    sample_count_failed_total = sum(entry.sample_count_failed for entry in entries)

    return DeliberationCampaignComparisonSummary(
        campaign_count=len(entries),
        campaign_ids=campaign_ids,
        status_counts=dict(status_counts),
        topic_values=topic_values,
        mode_values=mode_values,
        runtime_values=runtime_values,
        engine_values=engine_values,
        sample_count_values=sample_count_values,
        stability_runs_values=stability_runs_values,
        comparison_key_values=comparison_key_values,
        comparable=not mismatch_reasons,
        mismatch_reasons=mismatch_reasons,
        quality_score_mean=mean(quality_score_means) if quality_score_means else 0.0,
        quality_score_min=min(quality_score_means) if quality_score_means else 0.0,
        quality_score_max=max(quality_score_means) if quality_score_means else 0.0,
        confidence_level_mean=mean(confidence_level_means) if confidence_level_means else 0.0,
        confidence_level_min=min(confidence_level_means) if confidence_level_means else 0.0,
        confidence_level_max=max(confidence_level_means) if confidence_level_means else 0.0,
        sample_count_requested_total=sample_count_requested_total,
        sample_count_completed_total=sample_count_completed_total,
        sample_count_failed_total=sample_count_failed_total,
        metadata={
            "campaign_ids": campaign_ids,
            "comparison_key": comparison_key_values[0] if len(comparison_key_values) == 1 else None,
            "report_paths": [report.report_path for report in reports if report.report_path],
        },
    )


def _matrix_benchmark_export_comparison_entry_from_export(
    export: DeliberationCampaignMatrixBenchmarkExport,
) -> DeliberationCampaignMatrixBenchmarkExportComparisonEntry:
    metadata = dict(export.metadata or {}) if isinstance(export.metadata, dict) else {}
    return DeliberationCampaignMatrixBenchmarkExportComparisonEntry(
        export_id=export.export_id,
        created_at=export.created_at,
        benchmark_id=_normalize_text(export.benchmark_id),
        benchmark_report_path=_normalize_text(export.benchmark_report_path) or None,
        format=_normalize_text(export.format) or "markdown",
        baseline_campaign_id=_normalize_text(metadata.get("baseline_campaign_id")),
        baseline_runtime=_normalize_text(metadata.get("baseline_runtime")),
        baseline_engine=_normalize_text(
            metadata.get("baseline_engine_preference") or metadata.get("baseline_engine")
        ),
        candidate_count=int(export.candidate_count or 0),
        candidate_labels=[_normalize_text(label) for label in export.candidate_labels if _normalize_text(label)],
        candidate_campaign_ids=[
            _normalize_text(candidate_campaign_id)
            for candidate_campaign_id in export.candidate_campaign_ids
            if _normalize_text(candidate_campaign_id)
        ],
        comparison_ids=[_normalize_text(comparison_id) for comparison_id in export.comparison_ids if _normalize_text(comparison_id)],
        candidate_structure_key=_matrix_benchmark_export_candidate_structure_key(export),
        comparable=bool(export.comparable),
        comparable_count=int(export.comparable_count or 0),
        mismatch_count=int(export.mismatch_count or 0),
        mismatch_reasons=[_normalize_text(reason) for reason in export.mismatch_reasons if _normalize_text(reason)],
        quality_score_mean=float(export.quality_score_mean or 0.0),
        confidence_level_mean=float(export.confidence_level_mean or 0.0),
        best_candidate_label=_normalize_text(export.best_candidate_label),
        worst_candidate_label=_normalize_text(export.worst_candidate_label),
        manifest_path=_normalize_text(export.manifest_path) or None,
        content_path=_normalize_text(export.content_path) or None,
        metadata={
            **metadata,
            "benchmark_id": export.benchmark_id,
            "benchmark_report_path": export.benchmark_report_path,
            "candidate_structure_key": _matrix_benchmark_export_candidate_structure_key(export),
        },
    )


def _matrix_benchmark_comparison_entry_from_report(
    report: DeliberationCampaignMatrixBenchmarkBundle,
) -> DeliberationCampaignMatrixBenchmarkComparisonEntry:
    candidate_labels = [
        _normalize_text(candidate_spec.label) or f"candidate_{index:02d}"
        for index, candidate_spec in enumerate(report.candidate_specs, start=1)
    ]
    candidate_runtimes = [
        _normalize_text(candidate_spec.runtime)
        for candidate_spec in report.candidate_specs
        if _normalize_text(candidate_spec.runtime)
    ]
    candidate_engines = [
        _normalize_engine(candidate_spec.engine_preference).value
        for candidate_spec in report.candidate_specs
    ]
    candidate_structure_key = _matrix_benchmark_candidate_structure_key(report)
    baseline_campaign = report.baseline_campaign
    return DeliberationCampaignMatrixBenchmarkComparisonEntry(
        benchmark_id=report.benchmark_id,
        created_at=report.created_at,
        baseline_campaign_id=baseline_campaign.campaign_id,
        topic=_normalize_text(baseline_campaign.topic),
        mode=baseline_campaign.mode.value,
        baseline_runtime=_normalize_text(baseline_campaign.runtime_requested),
        baseline_engine=_normalize_text(baseline_campaign.engine_requested),
        sample_count_requested=int(baseline_campaign.sample_count_requested),
        stability_runs=int(baseline_campaign.stability_runs),
        candidate_count=int(report.summary.candidate_count),
        candidate_labels=candidate_labels,
        candidate_runtimes=candidate_runtimes,
        candidate_engines=candidate_engines,
        candidate_structure_key=candidate_structure_key,
        comparison_ids=list(report.summary.comparison_ids),
        comparable_count=int(report.summary.comparable_count),
        mismatch_count=int(report.summary.mismatch_count),
        quality_score_mean=float(report.summary.quality_score_mean),
        quality_score_min=float(report.summary.quality_score_min),
        quality_score_max=float(report.summary.quality_score_max),
        confidence_level_mean=float(report.summary.confidence_level_mean),
        confidence_level_min=float(report.summary.confidence_level_min),
        confidence_level_max=float(report.summary.confidence_level_max),
        report_path=report.report_path,
        metadata={
            "baseline_campaign_id": baseline_campaign.campaign_id,
            "candidate_campaign_ids": list(report.summary.candidate_campaign_ids),
            "candidate_labels": candidate_labels,
            "comparison_ids": list(report.summary.comparison_ids),
            "candidate_structure_key": candidate_structure_key,
        },
    )


def _matrix_benchmark_export_comparison_summary_from_entries(
    entries: list[DeliberationCampaignMatrixBenchmarkExportComparisonEntry],
    exports: list[DeliberationCampaignMatrixBenchmarkExport],
) -> DeliberationCampaignMatrixBenchmarkExportComparisonSummary:
    export_ids = [entry.export_id for entry in entries]
    benchmark_ids = [entry.benchmark_id for entry in entries if _normalize_text(entry.benchmark_id)]
    format_values = _sorted_unique_values(entry.format for entry in entries)
    baseline_runtime_values = _sorted_unique_values(entry.baseline_runtime for entry in entries)
    baseline_engine_values = _sorted_unique_values(entry.baseline_engine for entry in entries)
    candidate_count_values = _sorted_unique_values((entry.candidate_count for entry in entries), key=int)
    candidate_structure_key_values = _sorted_unique_values(entry.candidate_structure_key for entry in entries)
    mismatch_reasons: list[str] = []

    if len(baseline_runtime_values) > 1:
        mismatch_reasons.append("baseline_runtime_mismatch")
    if len(baseline_engine_values) > 1:
        mismatch_reasons.append("baseline_engine_mismatch")
    if len(candidate_count_values) > 1:
        mismatch_reasons.append("candidate_count_mismatch")
    if len(candidate_structure_key_values) > 1:
        mismatch_reasons.append("candidate_structure_mismatch")

    quality_score_means = [entry.quality_score_mean for entry in entries]
    confidence_level_means = [entry.confidence_level_mean for entry in entries]
    comparable_export_count = sum(1 for entry in entries if entry.comparable)
    mismatch_export_count = len(entries) - comparable_export_count
    candidate_count_total = sum(entry.candidate_count for entry in entries)
    comparable_candidate_total = sum(entry.comparable_count for entry in entries)
    mismatch_candidate_total = sum(entry.mismatch_count for entry in entries)

    return DeliberationCampaignMatrixBenchmarkExportComparisonSummary(
        export_count=len(entries),
        export_ids=export_ids,
        benchmark_ids=_sorted_unique_values(benchmark_ids),
        format_values=format_values,
        baseline_runtime_values=baseline_runtime_values,
        baseline_engine_values=baseline_engine_values,
        candidate_count_values=candidate_count_values,
        candidate_structure_key_values=candidate_structure_key_values,
        comparable=not mismatch_reasons,
        mismatch_reasons=mismatch_reasons,
        comparable_export_count=comparable_export_count,
        mismatch_export_count=mismatch_export_count,
        candidate_count_total=candidate_count_total,
        comparable_candidate_total=comparable_candidate_total,
        mismatch_candidate_total=mismatch_candidate_total,
        quality_score_mean=mean(quality_score_means) if quality_score_means else 0.0,
        quality_score_min=min(quality_score_means) if quality_score_means else 0.0,
        quality_score_max=max(quality_score_means) if quality_score_means else 0.0,
        confidence_level_mean=mean(confidence_level_means) if confidence_level_means else 0.0,
        confidence_level_min=min(confidence_level_means) if confidence_level_means else 0.0,
        confidence_level_max=max(confidence_level_means) if confidence_level_means else 0.0,
        metadata={
            "export_ids": export_ids,
            "candidate_structure_key": candidate_structure_key_values[0]
            if len(candidate_structure_key_values) == 1
            else None,
            "manifest_paths": [export.manifest_path for export in exports if export.manifest_path],
        },
    )


def _matrix_benchmark_comparison_summary_from_entries(
    entries: list[DeliberationCampaignMatrixBenchmarkComparisonEntry],
    reports: list[DeliberationCampaignMatrixBenchmarkBundle],
) -> DeliberationCampaignMatrixBenchmarkComparisonSummary:
    benchmark_ids = [entry.benchmark_id for entry in entries]
    status_counts = Counter("comparable" if entry.mismatch_count == 0 else "mismatch" for entry in entries)
    topic_values = _sorted_unique_values(entry.topic for entry in entries)
    mode_values = _sorted_unique_values(entry.mode for entry in entries)
    baseline_runtime_values = _sorted_unique_values(entry.baseline_runtime for entry in entries)
    baseline_engine_values = _sorted_unique_values(entry.baseline_engine for entry in entries)
    runtime_values = _sorted_unique_values(
        value
        for entry in entries
        for value in [entry.baseline_runtime, *entry.candidate_runtimes]
        if _normalize_text(value)
    )
    engine_values = _sorted_unique_values(
        value
        for entry in entries
        for value in [entry.baseline_engine, *entry.candidate_engines]
        if _normalize_text(value)
    )
    sample_count_values = _sorted_unique_values((entry.sample_count_requested for entry in entries), key=int)
    stability_runs_values = _sorted_unique_values((entry.stability_runs for entry in entries), key=int)
    candidate_count_values = _sorted_unique_values((entry.candidate_count for entry in entries), key=int)
    candidate_structure_key_values = _sorted_unique_values(entry.candidate_structure_key for entry in entries)
    mismatch_reasons: list[str] = []

    if len(topic_values) > 1:
        mismatch_reasons.append("topic_mismatch")
    if len(mode_values) > 1:
        mismatch_reasons.append("mode_mismatch")
    if len(baseline_runtime_values) > 1:
        mismatch_reasons.append("baseline_runtime_mismatch")
    if len(baseline_engine_values) > 1:
        mismatch_reasons.append("baseline_engine_mismatch")
    if len(sample_count_values) > 1:
        mismatch_reasons.append("sample_count_mismatch")
    if len(stability_runs_values) > 1:
        mismatch_reasons.append("stability_runs_mismatch")
    if len(candidate_count_values) > 1:
        mismatch_reasons.append("candidate_count_mismatch")
    if len(candidate_structure_key_values) > 1:
        mismatch_reasons.append("candidate_structure_mismatch")

    quality_score_means = [entry.quality_score_mean for entry in entries]
    confidence_level_means = [entry.confidence_level_mean for entry in entries]
    candidate_count_total = sum(entry.candidate_count for entry in entries)
    comparable_count_total = sum(entry.comparable_count for entry in entries)
    mismatch_count_total = sum(entry.mismatch_count for entry in entries)

    return DeliberationCampaignMatrixBenchmarkComparisonSummary(
        benchmark_count=len(entries),
        benchmark_ids=benchmark_ids,
        status_counts=dict(status_counts),
        topic_values=topic_values,
        mode_values=mode_values,
        baseline_runtime_values=baseline_runtime_values,
        baseline_engine_values=baseline_engine_values,
        runtime_values=runtime_values,
        engine_values=engine_values,
        sample_count_values=sample_count_values,
        stability_runs_values=stability_runs_values,
        candidate_count_values=candidate_count_values,
        candidate_structure_key_values=candidate_structure_key_values,
        comparable=not mismatch_reasons,
        mismatch_reasons=mismatch_reasons,
        quality_score_mean=mean(quality_score_means) if quality_score_means else 0.0,
        quality_score_min=min(quality_score_means) if quality_score_means else 0.0,
        quality_score_max=max(quality_score_means) if quality_score_means else 0.0,
        confidence_level_mean=mean(confidence_level_means) if confidence_level_means else 0.0,
        confidence_level_min=min(confidence_level_means) if confidence_level_means else 0.0,
        confidence_level_max=max(confidence_level_means) if confidence_level_means else 0.0,
        candidate_count_total=candidate_count_total,
        comparable_count_total=comparable_count_total,
        mismatch_count_total=mismatch_count_total,
        metadata={
            "benchmark_ids": benchmark_ids,
            "candidate_structure_key": candidate_structure_key_values[0]
            if len(candidate_structure_key_values) == 1
            else None,
            "report_paths": [report.report_path for report in reports if report.report_path],
        },
    )


def _sample_summary_from_result(
    result: DeliberationResult,
    *,
    sample_id: str,
    sample_index: int,
    result_path: str | None,
    campaign_id: str,
    sample_count: int,
    stability_runs: int,
    requested_allow_fallback: bool,
    effective_allow_fallback: bool,
    fallback_guard_applied: bool,
    fallback_guard_reason: str | None,
) -> DeliberationCampaignSample:
    metadata = dict(getattr(result, "metadata", {}) or {}) if isinstance(getattr(result, "metadata", None), dict) else {}
    comparability = dict(metadata.get("comparability") or {})
    comparability.update(
        {
            "campaign_id": campaign_id,
            "sample_id": sample_id,
            "sample_index": sample_index,
            "sample_count_requested": sample_count,
            "stability_runs": stability_runs,
            "allow_fallback_requested": requested_allow_fallback,
            "allow_fallback_effective": effective_allow_fallback,
            "campaign_fallback_guard_applied": fallback_guard_applied,
            "campaign_fallback_guard_reason": fallback_guard_reason,
        }
    )
    quality_warnings = _normalize_text_list(metadata.get("quality_warnings"))
    runtime_resilience = metadata.get("runtime_resilience")
    stability_summary = getattr(result, "stability_summary", None)
    if hasattr(stability_summary, "model_dump"):
        stability_summary = stability_summary.model_dump(mode="json")
    return DeliberationCampaignSample(
        sample_id=sample_id,
        sample_index=sample_index,
        deliberation_id=_normalize_text(getattr(result, "deliberation_id", "")),
        status=_normalize_text(getattr(getattr(result, "status", None), "value", getattr(result, "status", "unknown"))),
        topic=_normalize_text(getattr(result, "topic", "")),
        objective=_normalize_text(getattr(result, "objective", "")),
        summary=_normalize_text(getattr(result, "summary", "")),
        final_strategy=_normalize_text(getattr(result, "final_strategy", "")),
        runtime_requested=_normalize_text(getattr(result, "runtime_requested", "")),
        runtime_used=_normalize_text(getattr(result, "runtime_used", None)) or None,
        fallback_used=bool(getattr(result, "fallback_used", False)),
        engine_requested=_normalize_text(getattr(result, "engine_requested", None)) or None,
        engine_used=_normalize_text(getattr(result, "engine_used", None)) or None,
        quality_score=_result_quality_score(result),
        confidence_level=_result_confidence_level(result),
        runtime_resilience=runtime_resilience if isinstance(runtime_resilience, dict) else None,
        stability_summary=stability_summary if isinstance(stability_summary, dict) else None,
        comparability=comparability,
        quality_warnings=quality_warnings,
        result_path=result_path,
    )


def _persist_sample_result(result: DeliberationResult, sample_dir: Path) -> str:
    sample_dir.mkdir(parents=True, exist_ok=True)
    result_path = sample_dir / "result.json"
    result_path.write_text(json.dumps(_result_payload(result), indent=2, sort_keys=True), encoding="utf-8")
    return str(result_path)


def _result_payload(result: DeliberationResult) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        try:
            payload = result.model_dump(mode="json")
            if isinstance(payload, dict):
                return payload
        except TypeError:
            payload = result.model_dump()
            if isinstance(payload, dict):
                return payload
    if isinstance(result, dict):
        return dict(result)
    return _jsonable_dict(getattr(result, "__dict__", {}))


def _jsonable_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {key: _jsonable(value) for key, value in value.items()}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return _jsonable_dict(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted(_jsonable(item) for item in value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(mode="json")
        except TypeError:
            return value.model_dump()
    return value


def _normalize_mode(mode: DeliberationMode | str) -> DeliberationMode:
    if isinstance(mode, DeliberationMode):
        return mode
    return DeliberationMode(str(mode).strip().lower())


def _normalize_engine(engine: EnginePreference | str) -> EnginePreference:
    if isinstance(engine, EnginePreference):
        return engine
    return EnginePreference(str(engine).strip().lower())


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        value = value.value
    return " ".join(str(value).split())


def _normalize_text_list(value: Any) -> list[str]:
    if not value:
        return []
    if not isinstance(value, (list, tuple, set)):
        value = [value]
    return [_normalize_text(item) for item in value if _normalize_text(item)]


def _result_quality_score(result: DeliberationResult) -> float:
    judge_scores = getattr(result, "judge_scores", None)
    overall = getattr(judge_scores, "overall", None)
    if overall not in (None, 0.0):
        return float(overall)
    confidence_level = getattr(result, "confidence_level", None)
    if confidence_level is not None:
        return float(confidence_level)
    return 0.0


def _result_confidence_level(result: DeliberationResult) -> float:
    confidence_level = getattr(result, "confidence_level", None)
    if confidence_level is not None:
        return float(confidence_level)
    judge_scores = getattr(result, "judge_scores", None)
    overall = getattr(judge_scores, "overall", None)
    if overall is not None:
        return float(overall)
    return 0.0


def _campaign_status_from_samples(samples: list[DeliberationCampaignSample]) -> DeliberationCampaignStatus:
    if not samples:
        return DeliberationCampaignStatus.failed
    failed = sum(1 for sample in samples if sample.status == DeliberationCampaignStatus.failed.value)
    if failed == 0:
        return DeliberationCampaignStatus.completed
    if failed == len(samples):
        return DeliberationCampaignStatus.failed
    return DeliberationCampaignStatus.partial


def _campaign_comparison_key(
    *,
    topic: str,
    objective: str,
    mode: DeliberationMode,
    runtime: str,
    engine_preference: EnginePreference,
    sample_count: int,
    stability_runs: int,
) -> str:
    return "|".join(
        [
            f"topic={_normalize_text(topic)}",
            f"objective={_normalize_text(objective)}",
            f"mode={mode.value}",
            f"runtime={_normalize_text(runtime)}",
            f"engine={engine_preference.value}",
            f"samples={sample_count}",
            f"stability_runs={stability_runs}",
        ]
    )


def _matrix_benchmark_candidate_structure_key(
    report: DeliberationCampaignMatrixBenchmarkBundle,
) -> str:
    signature_items = [
        "|".join(
            [
                f"label={_normalize_text(candidate_spec.label) or f'candidate_{index:02d}'}",
                f"runtime={_normalize_text(candidate_spec.runtime)}",
                f"engine={_normalize_engine(candidate_spec.engine_preference).value}",
            ]
        )
        for index, candidate_spec in enumerate(report.candidate_specs, start=1)
    ]
    return "||".join(sorted(signature_items))


def _campaign_report_path(campaign_id: str, *, output_dir: str | Path | None = None) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR)
    return base_dir / campaign_id / "report.json"


def _comparison_report_path(comparison_id: str, *, output_dir: str | Path | None = None) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR)
    return base_dir / comparison_id / "report.json"


def _normalize_campaign_status(status: DeliberationCampaignStatus | str) -> DeliberationCampaignStatus:
    if isinstance(status, DeliberationCampaignStatus):
        return status
    return DeliberationCampaignStatus(str(status).strip().lower())


def _campaign_created_at_sort_key(created_at: datetime) -> float:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at.timestamp()


def _sorted_unique_values(values: Any, *, key: Callable[[Any], Any] | None = None) -> list[Any]:
    unique_values = list(dict.fromkeys(values))
    if key is None:
        return unique_values
    return sorted(unique_values, key=key)


def _report_comparison_key(report: DeliberationCampaignReport) -> str:
    stability_summary = report.summary.campaign_stability_summary
    if stability_summary:
        comparison_key = _normalize_text(getattr(stability_summary, "comparison_key", ""))
        if comparison_key:
            return comparison_key
    metadata_comparison_key = _normalize_text(report.metadata.get("comparison_key"))
    if metadata_comparison_key:
        return metadata_comparison_key
    summary_metadata_comparison_key = _normalize_text(report.summary.metadata.get("comparison_key"))
    if summary_metadata_comparison_key:
        return summary_metadata_comparison_key
    return ""


__all__ = [
    "DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR",
    "DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR",
    "DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR",
    "DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR",
    "DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR",
    "DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR",
    "DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR",
    "DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_OUTPUT_DIR",
    "DeliberationCampaignArtifactIndex",
    "DeliberationCampaignDashboard",
    "DeliberationCampaignDashboardRow",
    "DeliberationCampaignComparisonEntry",
    "DeliberationCampaignComparisonAudit",
    "DeliberationCampaignComparisonBundle",
    "DeliberationCampaignBenchmarkBundle",
    "DeliberationCampaignMatrixBenchmarkBundle",
    "DeliberationCampaignMatrixBenchmarkAudit",
    "DeliberationCampaignMatrixBenchmarkAuditEntry",
    "DeliberationCampaignMatrixBenchmarkAuditSummary",
    "DeliberationCampaignMatrixBenchmarkExport",
    "DeliberationCampaignMatrixBenchmarkSummary",
    "DeliberationCampaignMatrixCandidateSpec",
    "DeliberationCampaignMatrixComparisonEntry",
    "DeliberationCampaignMatrixBenchmarkComparisonEntry",
    "DeliberationCampaignMatrixBenchmarkComparisonAudit",
    "DeliberationCampaignMatrixBenchmarkComparisonBundle",
    "DeliberationCampaignMatrixBenchmarkComparisonExport",
    "DeliberationCampaignMatrixBenchmarkComparisonReport",
    "DeliberationCampaignMatrixBenchmarkComparisonSummary",
    "DeliberationCampaignComparisonExport",
    "DeliberationCampaignComparisonReport",
    "DeliberationCampaignComparisonSummary",
    "DeliberationCampaignReport",
    "DeliberationCampaignSample",
    "DeliberationCampaignStatus",
    "DeliberationCampaignSummary",
    "build_deliberation_campaign_comparison_audit",
    "build_deliberation_campaign_artifact_index",
    "build_deliberation_campaign_dashboard",
    "build_deliberation_campaign_matrix_benchmark_audit",
    "build_deliberation_campaign_matrix_benchmark_export",
    "build_deliberation_campaign_matrix_benchmark_comparison_audit",
    "compare_deliberation_campaign_bundle",
    "compare_deliberation_campaign_matrix_benchmarks",
    "compare_deliberation_campaign_matrix_benchmark_comparison_bundle",
    "run_deliberation_campaign_benchmark_sync",
    "run_deliberation_campaign_matrix_benchmark_sync",
    "build_deliberation_campaign_comparison_export",
    "build_deliberation_campaign_matrix_benchmark_comparison_export",
    "compare_deliberation_campaign_reports",
    "load_deliberation_campaign_benchmark",
    "load_deliberation_campaign_matrix_benchmark_audit",
    "load_deliberation_campaign_matrix_benchmark_comparison_report",
    "load_deliberation_campaign_matrix_benchmark_comparison_audit",
    "load_deliberation_campaign_matrix_benchmark_comparison_export",
    "load_deliberation_campaign_matrix_benchmark_export",
    "load_deliberation_campaign_matrix_benchmark",
    "load_deliberation_campaign_comparison_audit",
    "load_deliberation_campaign_comparison_export",
    "load_deliberation_campaign_comparison_report",
    "load_deliberation_campaign_report",
    "list_deliberation_campaign_benchmarks",
    "list_deliberation_campaign_matrix_benchmark_audits",
    "list_deliberation_campaign_matrix_benchmark_comparison_reports",
    "list_deliberation_campaign_matrix_benchmark_comparison_exports",
    "list_deliberation_campaign_matrix_benchmark_exports",
    "list_deliberation_campaign_matrix_benchmarks",
    "list_deliberation_campaign_comparison_reports",
    "list_deliberation_campaign_comparison_exports",
    "list_deliberation_campaign_reports",
    "materialize_deliberation_campaign_comparison_export",
    "materialize_deliberation_campaign_matrix_benchmark_export",
    "materialize_deliberation_campaign_matrix_benchmark_comparison_export",
    "run_deliberation_campaign_sync",
    "render_deliberation_campaign_comparison_markdown",
    "render_deliberation_campaign_matrix_benchmark_markdown",
    "render_deliberation_campaign_matrix_benchmark_comparison_markdown",
]
