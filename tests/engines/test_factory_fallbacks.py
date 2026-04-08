from __future__ import annotations

from simulation_adapter.factory import build_default_adapter_service, describe_backend


def test_default_adapter_service_falls_back_to_surrogates_when_live_is_unavailable(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "simulation_adapter.factory.AgentSocietyProcessClient.from_environment",
        classmethod(lambda cls: (_ for _ in ()).throw(RuntimeError("agentsociety missing"))),
    )
    monkeypatch.setattr(
        "simulation_adapter.factory.OASISProcessClient.from_environment",
        classmethod(lambda cls: (_ for _ in ()).throw(RuntimeError("oasis missing"))),
    )

    service = build_default_adapter_service(str(tmp_path / "runs.db"))

    registered = {engine.value: describe_backend(adapter) for engine, adapter in service.adapters.items()}
    assert registered["agentsociety"] == "surrogate"
    assert registered["oasis"] == "surrogate"
