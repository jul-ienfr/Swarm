from __future__ import annotations

from pathlib import Path

from engines.oasis.live_client import OASISModelConfig, OASISProcessClient
from engines.oasis.translator import OASISRunConfig


def test_oasis_from_environment_uses_docker_when_package_missing(monkeypatch) -> None:
    monkeypatch.setattr("engines.oasis.live_client.find_spec", lambda name: None)
    monkeypatch.setattr("engines.oasis.live_client._docker_live_available", lambda: True)
    monkeypatch.setattr(
        "engines.oasis.live_client._load_model_config",
        lambda: OASISModelConfig(
            base_url="https://example.com/v1",
            api_key="test-key",
            model_name="test-model",
            source="test",
        ),
    )

    client = OASISProcessClient.from_environment()

    assert client._execution_mode == "docker"
    assert client._model_config is not None
    assert client._model_config.model_name == "test-model"


def test_oasis_docker_mode_create_run_and_result(tmp_path: Path, monkeypatch) -> None:
    client = OASISProcessClient(
        runs_root=tmp_path / "runs",
        database_path=tmp_path / "oasis.db",
        execution_mode="docker",
        model_config=OASISModelConfig(
            base_url="https://example.com/v1",
            api_key="test-key",
            model_name="test-model",
            source="test",
        ),
        repo_root=tmp_path,
    )

    async def fake_execute(config: OASISRunConfig, *, run_dir: Path) -> None:
        (run_dir / "report.json").write_text(
            '{"platform":"reddit","execution_mode":"docker"}',
            encoding="utf-8",
        )

    monkeypatch.setattr(client, "_execute_live_run_docker", fake_execute)
    monkeypatch.setattr("engines.oasis.live_client._package_version", lambda: "0.2.5")

    engine_run_id = client.create_run(
        OASISRunConfig(
            run_id="run_1",
            platform="reddit",
            database_path="/tmp/oasis.db",
            agent_count=4,
            time_horizon="1d",
            topic="Test topic",
            objective="Test objective",
        )
    )

    status = client.get_run_status(engine_run_id)
    result = client.get_result(engine_run_id)

    assert status.status == "COMPLETED"
    assert result.summary
    assert result.engine_version == "0.2.5"
    assert result.artifacts


def test_oasis_docker_mode_marks_failed_on_runtime_error(tmp_path: Path, monkeypatch) -> None:
    client = OASISProcessClient(
        runs_root=tmp_path / "runs",
        database_path=tmp_path / "oasis.db",
        execution_mode="docker",
        model_config=OASISModelConfig(
            base_url="https://example.com/v1",
            api_key="test-key",
            model_name="test-model",
            source="test",
        ),
        repo_root=tmp_path,
    )

    async def fake_execute(config: OASISRunConfig, *, run_dir: Path) -> None:
        raise RuntimeError("docker execution failed")

    monkeypatch.setattr(client, "_execute_live_run_docker", fake_execute)

    engine_run_id = client.create_run(
        OASISRunConfig(
            run_id="run_2",
            platform="reddit",
            database_path="/tmp/oasis.db",
            agent_count=4,
            time_horizon="1d",
            topic="Test topic",
            objective="Test objective",
        )
    )

    status = client.get_run_status(engine_run_id)
    assert status.status == "FAILED"
    assert status.message == "docker execution failed"
