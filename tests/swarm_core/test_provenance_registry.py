from pathlib import Path

from swarm_core.provenance_registry import ProvenanceKind, ProvenanceRegistry


def test_provenance_registry_records_and_lineage(tmp_path: Path) -> None:
    storage = tmp_path / "provenance.json"
    registry = ProvenanceRegistry(storage)

    root = registry.record(
        run_id="run-1",
        kind=ProvenanceKind.document,
        subject_id="doc-1",
        source="ingest",
        details={"title": "seed"},
    )
    child = registry.record(
        run_id="run-1",
        kind="profile",
        subject_id="profile-1",
        source="profile-generator",
        parent_id=root.record_id,
    )

    assert registry.get(root.record_id) is not None
    assert registry.list(run_id="run-1")[0].record_id == root.record_id
    assert [entry.record_id for entry in registry.lineage(child.record_id)] == [child.record_id, root.record_id]
    assert storage.exists()


def test_provenance_registry_roundtrip(tmp_path: Path) -> None:
    storage = tmp_path / "provenance.json"
    registry = ProvenanceRegistry(storage)
    entry = registry.record(
        run_id="run-2",
        kind=ProvenanceKind.report,
        subject_id="report-1",
        source="deliberation",
        details={"summary": "ok"},
    )

    reloaded = ProvenanceRegistry(storage)
    loaded = reloaded.get(entry.record_id)
    assert loaded is not None
    assert loaded.subject_id == "report-1"
    assert loaded.details["summary"] == "ok"

