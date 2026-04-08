from __future__ import annotations

import sys
import types
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "swarm_core"
if "swarm_core" not in sys.modules:
    swarm_core_package = types.ModuleType("swarm_core")
    swarm_core_package.__path__ = [str(PACKAGE_ROOT)]
    sys.modules["swarm_core"] = swarm_core_package

from swarm_core.deliberation_artifacts import DeliberationMode
from swarm_core.deliberation_workbench import (
    DEFAULT_WORKBENCH_OUTPUT_DIR,
    WorkbenchStatus,
    build_workbench_session,
    load_workbench_session,
    persist_workbench_session,
    profile_to_belief_state,
    profiles_to_graph_payload,
    workbench_directory,
)


def test_workbench_builds_normalized_input_and_profiles() -> None:
    session = build_workbench_session(
        topic="How should we launch the product?",
        objective="Choose a launch strategy.",
        mode=DeliberationMode.hybrid,
        participants=["architect", "research", "safety"],
        documents=["Signal A", "Signal B"],
        interventions=["Inject a moderation change."],
        population_size=120,
        rounds=3,
    )

    assert session.input_bundle.schema_version == "v1"
    assert session.input_bundle.mode == DeliberationMode.hybrid
    assert session.status == WorkbenchStatus.prepared
    assert len(session.profiles) == 3
    assert session.metadata["participant_source"] == "explicit"
    assert session.metadata["profile_generation_version"] == "v2"
    assert session.metadata["signal_keywords"]
    assert all(profile.evidence for profile in session.profiles)
    assert all(profile.metadata["participant_source"] == "explicit" for profile in session.profiles)
    assert all(profile.summary.startswith(profile.label) for profile in session.profiles)
    assert session.summary.startswith("Workbench for 'How should we launch the product?'")


def test_workbench_derives_semantic_participants_when_none_are_provided() -> None:
    session = build_workbench_session(
        topic="Revue du plan d'integration exhaustive des patterns externes pour prediction_markets",
        objective="Identifier ce qu'il faut integrer en priorite sans tout importer.",
        mode=DeliberationMode.hybrid,
        documents=[
            "Ce plan contient des patterns de stabilite, de qualite et de replay.",
            "L'objectif est de garder la fiabilite et la traceabilite.",
        ],
        interventions=["Ajouter des gates explicites et du red team."],
        population_size=96,
        rounds=3,
    )

    labels = [profile.label for profile in session.profiles]
    assert session.metadata["participant_source"] == "derived"
    assert len(labels) >= 3
    assert len(labels) == len(set(labels))
    assert all(label not in {"les", "plan", "patterns", "est", "pas"} for label in labels)
    assert any("_" in label for label in labels)
    assert session.metadata["signal_keywords"]
    assert all(profile.metadata["participant_source"] == "derived" for profile in session.profiles)
    assert all(profile.metadata["signal_count"] >= 1 for profile in session.profiles)
    assert session.summary.startswith("Workbench for 'Revue du plan d'integration exhaustive")


def test_workbench_persists_roundtrip_and_graph(tmp_path: Path) -> None:
    session = build_workbench_session(
        topic="Interview smoke",
        objective="Generate personas and a graph.",
        mode=DeliberationMode.simulation,
        documents=["Doc A", "Doc B"],
        entities=[{"segment": "early-adopters"}],
        interventions=["Inject an outage."],
        population_size=48,
        rounds=2,
    )

    persisted = persist_workbench_session(session, output_dir=tmp_path)

    assert persisted.status == WorkbenchStatus.persisted
    assert persisted.session_path is not None
    assert persisted.graph_path is not None
    assert Path(persisted.session_path).exists()
    assert Path(persisted.graph_path).exists()

    loaded = load_workbench_session(persisted.session_path)
    assert loaded.workbench_id == persisted.workbench_id
    assert loaded.input_bundle.topic == "Interview smoke"
    assert len(loaded.profiles) >= 3
    assert len(loaded.artifacts) >= 2
    assert loaded.metadata["participant_source"] == "derived"
    assert loaded.metadata["profile_generation_version"] == "v2"

    graph_payload = profiles_to_graph_payload(loaded.profiles)
    assert graph_payload["nodes"]
    assert graph_payload["edges"]

    belief_state = profile_to_belief_state(loaded.profiles[0])
    assert belief_state.agent_id == loaded.profiles[0].profile_id
    assert belief_state.memory_window


def test_workbench_directory_points_to_expected_location(tmp_path: Path) -> None:
    workbench_id = "wb_demo"
    directory = workbench_directory(output_dir=tmp_path, workbench_id=workbench_id)
    assert directory == tmp_path / workbench_id
    assert str(DEFAULT_WORKBENCH_OUTPUT_DIR).endswith("deliberation_workbench")
