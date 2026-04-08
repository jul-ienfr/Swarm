from __future__ import annotations

from pathlib import Path

from swarm_core.sliding_memory import SlidingMemoryEngine, SlidingMemoryEntry, SlidingMemoryWindow, compact_memory_texts


def test_sliding_memory_compacts_to_capacity() -> None:
    engine = SlidingMemoryEngine(owner_id="agent_1", capacity=3)
    engine.record("one", score=0.1, tags=["alpha"])
    engine.record("two", score=0.9, tags=["beta"])
    engine.record("three", score=0.8, tags=["gamma"])
    engine.record("four", score=0.7, tags=["delta"])

    snapshot = engine.compact().snapshot()

    assert snapshot.entry_count == 3
    assert snapshot.owner_id == "agent_1"
    assert snapshot.top_tags
    assert all(entry.text in {"two", "three", "four"} for entry in engine.window.entries)


def test_sliding_memory_search_prefers_relevant_entries() -> None:
    window = SlidingMemoryWindow(owner_id="agent_2", capacity=5)
    window.add_text("The release is strong and stable.", score=0.9, tags=["release", "stable"])
    window.add_text("We should delay the launch.", score=0.8, tags=["launch", "risk"])
    window.add_text("The forum discussion is neutral.", score=0.2, tags=["forum"])

    matches = window.search("launch risk", limit=2)

    assert len(matches) == 1
    assert matches[0].text == "We should delay the launch."


def test_sliding_memory_save_and_load_roundtrip(tmp_path: Path) -> None:
    engine = SlidingMemoryEngine(owner_id="agent_3", capacity=4)
    engine.extend(
        [
            SlidingMemoryEntry(actor_id="agent_3", text="Signal A", score=0.4, tags=["a"]),
            SlidingMemoryEntry(actor_id="agent_3", text="Signal B", score=0.6, tags=["b"]),
        ]
    )

    path = engine.save(tmp_path / "memory.json")
    loaded = SlidingMemoryWindow.load(path)

    assert loaded.owner_id == "agent_3"
    assert loaded.capacity == 4
    assert len(loaded.entries) == 2


def test_sliding_memory_compact_text_helper() -> None:
    compacted = compact_memory_texts(["a", "b", "c", "d"], capacity=2)
    assert len(compacted) == 2
