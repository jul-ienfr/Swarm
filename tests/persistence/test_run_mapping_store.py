from __future__ import annotations

from pathlib import Path

from runtime_contracts import RunStatus
from simulation_adapter.mapping_store import RunMappingStore


def test_run_mapping_store_survives_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "run_mappings.db"
    store_one = RunMappingStore(str(db_path))
    store_one.create("intent_1", "run_1", "agentsociety", "corr_1")
    store_one.update_engine_run_id("run_1", "as_run_abc")
    store_one.update_status("run_1", RunStatus.running)

    store_two = RunMappingStore(str(db_path))
    mapping = store_two.get_by_runtime_run_id("run_1")

    assert mapping is not None
    assert mapping.intent_id == "intent_1"
    assert mapping.runtime_run_id == "run_1"
    assert mapping.engine == "agentsociety"
    assert mapping.engine_run_id == "as_run_abc"
    assert mapping.status == RunStatus.running
    assert mapping.correlation_id == "corr_1"
