from __future__ import annotations

from typing import Protocol, TypeAlias

from pydantic import BaseModel, Field

from runtime_contracts.adapter_command import ControlParams, EngineTarget, SeedMaterials, SimulationParameters
from runtime_contracts.adapter_result import AdapterResultV1


class _BaseAdapterRequest(BaseModel):
    adapter_version: str = "v1"
    runtime_run_id: str
    engine: EngineTarget = EngineTarget.agentsociety
    correlation_id: str | None = None
    swarm_intent_id: str | None = None


class CreateRunRequest(_BaseAdapterRequest):
    simulation_type: str = "society"
    brief: str | None = None
    seed_materials: SeedMaterials = Field(default_factory=SeedMaterials)
    parameters: SimulationParameters = Field(default_factory=SimulationParameters)
    control: ControlParams = Field(default_factory=ControlParams)


class GetStatusRequest(_BaseAdapterRequest):
    pass


class GetResultRequest(_BaseAdapterRequest):
    pass


class CancelRunRequest(_BaseAdapterRequest):
    pass


CreateRunResponse: TypeAlias = AdapterResultV1
StatusResponse: TypeAlias = AdapterResultV1
ResultResponse: TypeAlias = AdapterResultV1
CancelRunResponse: TypeAlias = AdapterResultV1


class SimulationEngineAdapter(Protocol):
    def create_run(self, request: CreateRunRequest) -> CreateRunResponse: ...

    def get_status(self, request: GetStatusRequest) -> StatusResponse: ...

    def get_result(self, request: GetResultRequest) -> ResultResponse: ...

    def cancel_run(self, request: CancelRunRequest) -> CancelRunResponse: ...
