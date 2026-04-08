from __future__ import annotations

import os
from pathlib import Path

from engines.agentsociety import (
    AgentSocietyBenchmarkClient,
    AgentSocietyEngineAdapter,
    AgentSocietyProcessClient,
)
from engines.oasis import OASISBenchmarkClient, OASISEngineAdapter, OASISProcessClient
from runtime_contracts.adapter_command import EngineTarget

from .mapping_store import RunMappingStore
from .service import AdapterService


DEFAULT_RUNTIME_RUN_MAPPING_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "simulation_run_mappings.db"
)


def build_default_adapter_service(
    run_mapping_path: str | None = None,
    *,
    backend_mode: str | None = None,
) -> AdapterService:
    store = RunMappingStore(str(run_mapping_path or DEFAULT_RUNTIME_RUN_MAPPING_PATH))
    service = AdapterService(store=store)

    mode = _resolve_backend_mode(backend_mode)
    if mode == "disabled":
        return service

    if mode == "surrogate":
        _register_agentsociety_surrogate(service, store)
        _register_oasis_surrogate(service, store)
        return service

    try:
        live_client = AgentSocietyProcessClient.from_environment()
    except Exception:
        if explicit_live_mode(backend_mode):
            raise
        _register_agentsociety_surrogate(service, store)
    else:
        service.register_engine(
            EngineTarget.agentsociety,
            AgentSocietyEngineAdapter(
                live_client,
                store,
                artifact_base="/home/jul/.openclaw/workspace/langgraph-swarm/data/agentsociety/live-runs",
            ),
        )

    try:
        oasis_client = OASISProcessClient.from_environment()
    except Exception:
        _register_oasis_surrogate(service, store)
    else:
        service.register_engine(
            EngineTarget.oasis,
            OASISEngineAdapter(
                oasis_client,
                store,
                artifact_base="/home/jul/.openclaw/workspace/langgraph-swarm/data/oasis/live-runs",
            ),
        )
    return service


def describe_backend(adapter) -> str:
    client = getattr(adapter, "_client", None)
    if isinstance(client, AgentSocietyBenchmarkClient):
        return "surrogate"
    if isinstance(client, AgentSocietyProcessClient):
        return "live"
    if isinstance(client, OASISBenchmarkClient):
        return "surrogate"
    if isinstance(client, OASISProcessClient):
        return "live"
    return type(client).__name__ if client is not None else "unknown"


def _resolve_backend_mode(explicit_mode: str | None) -> str:
    if explicit_mode:
        return explicit_mode.strip().lower()

    for env_name in [
        "HARNESS_AGENTSOCIETY_BACKEND",
        "HARNESS_AGENTSOCIETY_BACKEND_MODE",
        "HARNESS_AGENTSOCIETY_MODE",
        "HARNESS_AGENTSOOCIETY_BACKEND",
        "HARNESS_AGENTSOOCIETY_BACKEND_MODE",
        "HARNESS_AGENTSOOCIETY_MODE",
    ]:
        raw = os.getenv(env_name, "").strip().lower()
        if raw:
            return raw
    return "live"


def explicit_live_mode(explicit_mode: str | None) -> bool:
    return bool(explicit_mode and explicit_mode.strip().lower() == "live")


def _register_agentsociety_surrogate(service: AdapterService, store: RunMappingStore) -> None:
    service.register_engine(
        EngineTarget.agentsociety,
        AgentSocietyEngineAdapter(
            AgentSocietyBenchmarkClient(),
            store,
            artifact_base="engine://agentsociety-surrogate",
        ),
    )


def _register_oasis_surrogate(service: AdapterService, store: RunMappingStore) -> None:
    service.register_engine(
        EngineTarget.oasis,
        OASISEngineAdapter(
            OASISBenchmarkClient(),
            store,
            artifact_base="engine://oasis-surrogate",
        ),
    )
