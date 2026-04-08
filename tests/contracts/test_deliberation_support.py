from __future__ import annotations

from pathlib import Path

import pytest

from swarm_core.deliberation_artifacts import (
    DeliberationArtifact,
    DeliberationArtifactKind,
    DeliberationMode,
    DeliberationProvenanceItem,
    DeliberationProvenanceKind,
    DeliberationRunManifest,
)
from swarm_core.deliberation_benchmark import (
    DeliberationBenchmarkCase,
    DeliberationBenchmarkExpectation,
    DeliberationBenchmarkOutcome,
    DeliberationBenchmarkReport,
    DeliberationBenchmarkSuite,
    DeliberationExpectationOperator,
)
from swarm_core.deliberation_replay import (
    DeliberationReplayEventKind,
    DeliberationReplayManifest,
)
from swarm_core.deliberation_stability import (
    DeliberationStabilitySample,
    DeliberationStabilitySummary,
)


def test_deliberation_manifest_roundtrip(tmp_path: Path) -> None:
    manifest = DeliberationRunManifest(
        run_id="run_001",
        topic="future of search",
        objective="produce a strategy",
        mode=DeliberationMode.hybrid,
        inputs={"population_size": 64},
        metadata={"owner": "qa"},
    )
    provenance = DeliberationProvenanceItem(
        provenance_id="prov_001",
        kind=DeliberationProvenanceKind.source,
        title="source note",
        source_uri="https://example.com/source",
        content="grounded note",
        confidence=0.83,
        parent_ids=["prov_root"],
        metadata={"source": "manual"},
    )
    artifact = DeliberationArtifact(
        artifact_id="art_001",
        kind=DeliberationArtifactKind.report,
        title="final report",
        uri="file:///tmp/report.json",
        content_hash="abc123",
        content_type="application/json",
        provenance_ids=["prov_001"],
        metadata={"stage": "final"},
    )
    manifest.add_provenance(provenance)
    manifest.add_artifact(artifact)

    path = tmp_path / "manifest.json"
    manifest.save(path)
    loaded = DeliberationRunManifest.load(path)

    assert loaded.run_id == "run_001"
    assert loaded.mode == DeliberationMode.hybrid
    assert loaded.inputs["population_size"] == 64
    assert loaded.metadata["owner"] == "qa"
    assert loaded.provenance[0].provenance_id == "prov_001"
    assert loaded.artifacts[0].kind == DeliberationArtifactKind.report
    assert loaded.artifacts[0].provenance_ids == ["prov_001"]
    assert loaded.updated_at >= loaded.created_at


def test_benchmark_suite_roundtrip_and_outcome_summary(tmp_path: Path) -> None:
    expectation = DeliberationBenchmarkExpectation(
        metric="score",
        operator=DeliberationExpectationOperator.gte,
        target=0.7,
        description="score must be good enough",
    )
    case = DeliberationBenchmarkCase(
        case_id="case_001",
        topic="market reaction",
        description="check forecast quality",
        mode=DeliberationMode.simulation,
        input_payload={"market": "news"},
        expectations=[expectation],
        tags=["forecast", "hybrid"],
        metadata={"priority": 1},
    )
    suite = DeliberationBenchmarkSuite(
        suite_id="suite_001",
        suite_version="v1",
        name="deliberation-regression",
        cases=[case],
        metadata={"owner": "qa"},
    )

    path = tmp_path / "suite.json"
    suite.save(path)
    loaded = DeliberationBenchmarkSuite.load(path)

    assert loaded.suite_id == "suite_001"
    assert loaded.case_ids() == ["case_001"]
    assert loaded.get_case("case_001").mode == DeliberationMode.simulation
    assert loaded.get_case("case_001").expectations[0].matches(0.8)
    assert not loaded.get_case("case_001").expectations[0].matches(0.6)

    outcomes = [
        DeliberationBenchmarkOutcome(case_id="case_001", passed=True, score=0.8, metrics={"score": 0.8}),
        DeliberationBenchmarkOutcome(case_id="case_002", passed=False, score=0.4, metrics={"score": 0.4}),
    ]
    report = DeliberationBenchmarkReport.from_outcomes(
        suite_id="suite_001",
        run_id="run_001",
        outcomes=outcomes,
        notes="mixed result",
        metadata={"batch": 1},
    )

    assert report.overall_score == pytest.approx(0.6)
    assert report.pass_rate == pytest.approx(0.5)
    assert report.notes == "mixed result"
    assert report.metadata["batch"] == 1


def test_replay_manifest_append_and_roundtrip(tmp_path: Path) -> None:
    replay = DeliberationReplayManifest(
        source_run_id="run_001",
        source_manifest_id="manifest_001",
        metadata={"scenario": "committee"},
    )
    first = replay.append_event(
        kind=DeliberationReplayEventKind.start,
        payload={"topic": "future of search"},
        provenance_ids=["prov_001"],
    )
    second = replay.append_event(
        kind=DeliberationReplayEventKind.turn,
        payload={"speaker": "agent_1", "message": "consider demand signals"},
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert replay.events_by_kind(DeliberationReplayEventKind.turn)[0].event_id == second.event_id

    path = tmp_path / "replay.json"
    replay.save(path)
    loaded = DeliberationReplayManifest.load(path)

    assert loaded.source_run_id == "run_001"
    assert loaded.source_manifest_id == "manifest_001"
    assert len(loaded.events) == 2
    assert loaded.events[1].kind == DeliberationReplayEventKind.turn


def test_stability_summary_derived_from_scores_and_samples() -> None:
    stable_summary = DeliberationStabilitySummary.from_scores(
        [0.92, 0.91, 0.93],
        threshold=0.05,
        metric_name="judge_overall",
        comparison_key="committee|judge_overall|v1",
        sample_run_ids=["run_a", "run_b", "run_c"],
        metadata={"mode": "committee", "runtime_used": "pydanticai"},
    )
    unstable_summary = DeliberationStabilitySummary.from_scores([0.2, 0.9], threshold=0.05)

    assert stable_summary.sample_count == 3
    assert stable_summary.stable is True
    assert stable_summary.sample_sufficient is True
    assert stable_summary.dispersion_gate_passed is True
    assert stable_summary.metric_name == "judge_overall"
    assert stable_summary.comparison_key == "committee|judge_overall|v1"
    assert stable_summary.sample_run_ids == ["run_a", "run_b", "run_c"]
    assert stable_summary.metadata["metric_name"] == "judge_overall"
    assert stable_summary.metadata["comparison_key"] == "committee|judge_overall|v1"
    assert stable_summary.metadata["sample_run_ids"] == ["run_a", "run_b", "run_c"]
    assert [sample.runtime_run_id for sample in stable_summary.samples] == ["run_a", "run_b", "run_c"]
    assert all(sample.metadata["metric_name"] == "judge_overall" for sample in stable_summary.samples)
    assert all(sample.metadata["comparison_key"] == "committee|judge_overall|v1" for sample in stable_summary.samples)
    assert stable_summary.mean_score == pytest.approx(0.92, rel=1e-3)
    assert stable_summary.score_spread == pytest.approx(0.02, rel=1e-3)
    assert unstable_summary.stable is False
    assert unstable_summary.sample_sufficient is True
    assert unstable_summary.dispersion_gate_passed is False
    assert unstable_summary.std_dev > 0.05

    samples = [
        DeliberationStabilitySample(score=0.51, runtime_run_id="r1", metadata={"source": "run_1"}),
        DeliberationStabilitySample(score=0.52, runtime_run_id="r2", metadata={"source": "run_2"}),
    ]
    sample_summary = DeliberationStabilitySummary.from_samples(
        samples,
        threshold=0.05,
        metric_name="confidence_level",
        metadata={"mode": "simulation"},
    )

    assert sample_summary.sample_count == 2
    assert sample_summary.metadata["sample_ids"] == [samples[0].sample_id, samples[1].sample_id]
    assert sample_summary.stable is True
    assert sample_summary.sample_sufficient is True
    assert sample_summary.minimum_sample_count == 2
    assert sample_summary.metric_name == "confidence_level"
    assert sample_summary.sample_run_ids == ["r1", "r2"]
    assert sample_summary.metadata["sample_run_ids"] == ["r1", "r2"]
    assert sample_summary.samples[0].metadata["source"] == "run_1"
    assert sample_summary.samples[0].metadata["comparison_key"] == sample_summary.comparison_key


def test_stability_summary_builds_default_comparison_key_and_validates_lengths() -> None:
    summary = DeliberationStabilitySummary.from_scores(
        [0.1, 0.2],
        metadata={"mode": "hybrid", "runtime_requested": "pydanticai"},
    )

    assert summary.metric_name == "overall"
    assert summary.comparison_key.startswith("metric=overall|threshold=0.1000|minimum_sample_count=2")
    assert "mode=hybrid" in summary.comparison_key
    assert "runtime=pydanticai" in summary.comparison_key
    assert summary.metadata["comparison_key"] == summary.comparison_key

    with pytest.raises(ValueError, match="sample_run_ids must match the number of scores"):
        DeliberationStabilitySummary.from_scores([0.1, 0.2], sample_run_ids=["only-one"])


def test_stability_summary_rejects_insufficient_samples() -> None:
    summary = DeliberationStabilitySummary.from_scores([0.48], threshold=0.05)

    assert summary.sample_count == 1
    assert summary.sample_sufficient is False
    assert summary.dispersion_gate_passed is True
    assert summary.stable is False
    assert any(flag.startswith("insufficient_samples:1/2") for flag in summary.assessment_flags)
    assert "sample_sufficient=False" in summary.notes


def test_stability_summary_rejects_wide_spread_even_with_low_variance() -> None:
    summary = DeliberationStabilitySummary.from_scores([0.10, 0.12, 0.11, 0.13, 0.90], threshold=0.35)

    assert summary.sample_count == 5
    assert summary.sample_sufficient is True
    assert summary.dispersion_gate_passed is False
    assert summary.stable is False
    assert summary.score_spread == pytest.approx(0.80, rel=1e-3)
    assert any(flag.startswith("score_spread_exceeds_threshold") for flag in summary.assessment_flags)
