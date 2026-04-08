from __future__ import annotations

from swarm_core.harness_memory import HarnessMemoryStore, MemoryEntryType


def test_harness_memory_store_persists_entries(tmp_path) -> None:
    store = HarnessMemoryStore(str(tmp_path / "harness_memory.db"))

    created = store.write_round_feedback(
        round_index=1,
        entry_type=MemoryEntryType.self_critique,
        summary="Round 1 critique",
        details={"issue": "engine_unavailable"},
        candidate_version="harness_candidate_v1",
        applied=False,
        score_delta=-0.1,
    )

    assert created.created_at is not None

    reopened = HarnessMemoryStore(str(tmp_path / "harness_memory.db"))
    entries = reopened.list_recent()

    assert len(entries) == 1
    assert entries[0].summary == "Round 1 critique"
    assert entries[0].details["issue"] == "engine_unavailable"
    assert reopened.get_latest_round_index() == 1


def test_harness_memory_store_detects_stagnation(tmp_path) -> None:
    store = HarnessMemoryStore(str(tmp_path / "harness_memory.db"))
    for round_index in range(1, 4):
        store.write_round_feedback(
            round_index=round_index,
            entry_type=MemoryEntryType.decision,
            summary=f"Round {round_index} reverted",
            details={"decision": "revert"},
            candidate_version=f"cand_{round_index}",
            applied=False,
            score_delta=0.0,
        )

    assert store.consecutive_non_improvements(3) == 3
