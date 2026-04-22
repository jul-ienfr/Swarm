from __future__ import annotations

from pathlib import Path


WORKFLOW_PATH = Path(".github/workflows/prediction-core-rust-runtime.yml")


def test_prediction_core_rust_runtime_workflow_exists_and_runs_xtask_bundle() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workflow = (repo_root / WORKFLOW_PATH).read_text()

    assert "name: prediction-core-rust-runtime" in workflow
    assert "workflow_dispatch:" in workflow
    assert "push:" in workflow
    assert "pull_request:" in workflow
    assert "prediction_core/rust/**" in workflow
    assert "tests/test_prediction_core_rust_" in workflow
    assert "cargo run -p xtask -- pm-storage-runtime" in workflow
    assert "./scripts/check_pm_storage_runtime.sh" not in workflow
    assert "docker" in workflow
    assert "working-directory: prediction_core/rust" in workflow
