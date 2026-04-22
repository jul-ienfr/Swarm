from __future__ import annotations

from pathlib import Path


REQUIRED_PATHS = [
    "prediction_core/README.md",
    "prediction_core/contracts/README.md",
    "prediction_core/python/README.md",
    "prediction_core/python/src/prediction_core/__init__.py",
    "prediction_core/python/tests/__init__.py",
    "prediction_core/rust/README.md",
    "prediction_core/rust/Cargo.toml",
    "prediction_core/rust/crates/live_engine/Cargo.toml",
    "prediction_core/rust/crates/live_engine/src/lib.rs",
    "prediction_core/rust/crates/pm_types/Cargo.toml",
    "prediction_core/rust/crates/pm_types/src/lib.rs",
    "prediction_core/rust/crates/pm_book/Cargo.toml",
    "prediction_core/rust/crates/pm_book/src/lib.rs",
    "prediction_core/rust/crates/pm_signal/Cargo.toml",
    "prediction_core/rust/crates/pm_signal/src/lib.rs",
    "prediction_core/rust/crates/pm_storage/Cargo.toml",
    "prediction_core/rust/crates/pm_storage/src/lib.rs",
    "prediction_core/rust/crates/pm_risk/Cargo.toml",
    "prediction_core/rust/crates/pm_risk/src/lib.rs",
    "prediction_core/rust/crates/pm_executor/Cargo.toml",
    "prediction_core/rust/crates/pm_executor/src/lib.rs",
    "prediction_core/rust/crates/pm_ledger/Cargo.toml",
    "prediction_core/rust/crates/pm_ledger/src/lib.rs",
]


def test_prediction_core_scaffold_exists() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    missing = [relative for relative in REQUIRED_PATHS if not (repo_root / relative).exists()]
    assert missing == []
