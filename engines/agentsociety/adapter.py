"""
Concrete AgentSociety engine adapter.
All AgentSociety-native objects remain local to this module family.
"""
from __future__ import annotations

from typing import Any

from runtime_contracts.adapter_result import (
    AdapterResultV1,
    EngineErrorCode,
    EngineMeta,
    NormalizedArtifact,
    NormalizedError,
    NormalizedMetric,
    RunStatus,
)
from simulation_adapter.adapter import (
    CancelRunRequest,
    CancelRunResponse,
    CreateRunRequest,
    CreateRunResponse,
    GetResultRequest,
    GetStatusRequest,
    ResultResponse,
    StatusResponse,
)
from simulation_adapter.errors import AdapterError, EngineUnavailableError
from simulation_adapter.mapping_store import RunMappingStore

from .monitor import AgentSocietyMonitor
from .translator import AgentSocietyTranslator


class AgentSocietyEngineAdapter:
    def __init__(self, engine_client, store: RunMappingStore, artifact_base: str = "/tmp/agentsociety"):
        self._client = engine_client
        self._store = store
        self._translator = AgentSocietyTranslator()
        self._monitor = AgentSocietyMonitor(engine_client=engine_client)
        self._artifact_base = artifact_base.rstrip("/")

    def create_run(self, request: CreateRunRequest) -> CreateRunResponse:
        config = self._translator.translate(request)
        try:
            engine_run_id = self._client.create_run(config)
        except Exception as exc:
            raise EngineUnavailableError(engine="agentsociety", detail=str(exc)) from exc

        self._store.update_engine_run_id(request.runtime_run_id, engine_run_id)
        self._store.update_status(request.runtime_run_id, RunStatus.queued)
        return AdapterResultV1(
            runtime_run_id=request.runtime_run_id,
            engine_run_id=engine_run_id,
            status=RunStatus.queued,
            correlation_id=request.correlation_id,
            engine_meta=EngineMeta(
                engine="agentsociety",
                adapter_version=request.adapter_version,
            ),
        )

    def get_status(self, request: GetStatusRequest) -> StatusResponse:
        mapping = self._store.get_by_runtime_run_id(request.runtime_run_id)
        if not mapping or not mapping.engine_run_id:
            return AdapterResultV1(
                runtime_run_id=request.runtime_run_id,
                status=RunStatus.failed,
                correlation_id=request.correlation_id,
                errors=[
                    NormalizedError.from_code(
                        EngineErrorCode.unknown,
                        "No engine_run_id found for runtime run.",
                    )
                ],
                engine_meta=EngineMeta(
                    engine="agentsociety",
                    adapter_version=request.adapter_version,
                ),
            )

        status, progress = self._monitor.poll(mapping.engine_run_id)
        self._store.update_status(request.runtime_run_id, status)
        return AdapterResultV1(
            runtime_run_id=request.runtime_run_id,
            engine_run_id=mapping.engine_run_id,
            status=status,
            progress=progress,
            correlation_id=request.correlation_id,
            engine_meta=EngineMeta(
                engine="agentsociety",
                adapter_version=request.adapter_version,
            ),
        )

    def get_result(self, request: GetResultRequest) -> ResultResponse:
        mapping = self._store.get_by_runtime_run_id(request.runtime_run_id)
        if not mapping or not mapping.engine_run_id:
            return AdapterResultV1(
                runtime_run_id=request.runtime_run_id,
                status=RunStatus.failed,
                correlation_id=request.correlation_id,
                errors=[
                    NormalizedError.from_code(
                        EngineErrorCode.unknown,
                        "No engine_run_id found for runtime run.",
                    )
                ],
                engine_meta=EngineMeta(
                    engine="agentsociety",
                    adapter_version=request.adapter_version,
                ),
            )

        current_status, progress = self._monitor.poll(mapping.engine_run_id)
        if current_status in {RunStatus.queued, RunStatus.running}:
            self._store.update_status(request.runtime_run_id, current_status)
            return AdapterResultV1(
                runtime_run_id=request.runtime_run_id,
                engine_run_id=mapping.engine_run_id,
                status=current_status,
                progress=progress,
                correlation_id=request.correlation_id,
                engine_meta=EngineMeta(
                    engine="agentsociety",
                    adapter_version=request.adapter_version,
                ),
            )
        if current_status in {
            RunStatus.cancelled,
            RunStatus.failed,
            RunStatus.timed_out,
            RunStatus.engine_unavailable,
        }:
            self._store.update_status(request.runtime_run_id, current_status)
            errors = []
            if current_status == RunStatus.failed:
                errors.append(
                    NormalizedError.from_code(
                        EngineErrorCode.unknown,
                        f"AgentSociety run finished with status '{current_status.value}'.",
                    )
                )
            return AdapterResultV1(
                runtime_run_id=request.runtime_run_id,
                engine_run_id=mapping.engine_run_id,
                status=current_status,
                progress=progress,
                correlation_id=request.correlation_id,
                errors=errors,
                engine_meta=EngineMeta(
                    engine="agentsociety",
                    adapter_version=request.adapter_version,
                ),
            )

        try:
            raw_result = self._client.get_result(mapping.engine_run_id)
        except AdapterError:
            raise
        except Exception as exc:
            raise AdapterError(
                code=EngineErrorCode.transient_failure,
                message=str(exc),
                retryable=True,
            ) from exc

        self._store.update_status(request.runtime_run_id, RunStatus.completed)
        return self._normalize_result(
            runtime_run_id=request.runtime_run_id,
            engine_run_id=mapping.engine_run_id,
            raw=raw_result,
            correlation_id=request.correlation_id,
            adapter_version=request.adapter_version,
        )

    def cancel_run(self, request: CancelRunRequest) -> CancelRunResponse:
        mapping = self._store.get_by_runtime_run_id(request.runtime_run_id)
        try:
            if mapping and mapping.engine_run_id:
                self._client.cancel_run(mapping.engine_run_id)
            self._store.update_status(request.runtime_run_id, RunStatus.cancelled)
            return AdapterResultV1(
                runtime_run_id=request.runtime_run_id,
                engine_run_id=mapping.engine_run_id if mapping else None,
                status=RunStatus.cancelled,
                correlation_id=request.correlation_id,
                engine_meta=EngineMeta(
                    engine="agentsociety",
                    adapter_version=request.adapter_version,
                ),
            )
        except Exception as exc:
            raise AdapterError(
                code=EngineErrorCode.transient_failure,
                message=str(exc),
                retryable=False,
            ) from exc

    def _normalize_result(
        self,
        *,
        runtime_run_id: str,
        engine_run_id: str,
        raw: Any,
        correlation_id: str | None,
        adapter_version: str,
    ) -> AdapterResultV1:
        raw_metrics = getattr(raw, "metrics", {})
        if isinstance(raw_metrics, dict):
            metrics = [
                NormalizedMetric(name=name, value=float(value), unit="index")
                for name, value in raw_metrics.items()
            ]
        else:
            metrics = []

        raw_artifacts = getattr(raw, "artifacts", [])
        artifacts = []
        for artifact in raw_artifacts:
            if not isinstance(artifact, dict):
                continue
            artifact_path = artifact.get("path", "output")
            uri = artifact.get("uri") or f"{self._artifact_base}/{engine_run_id}/{artifact_path}"
            artifacts.append(
                NormalizedArtifact(
                    name=artifact.get("name", "output"),
                    artifact_type=artifact.get("type", "dataset"),
                    uri=uri,
                    content_type=artifact.get("content_type"),
                )
            )

        return AdapterResultV1(
            runtime_run_id=runtime_run_id,
            engine_run_id=engine_run_id,
            status=RunStatus.completed,
            summary=getattr(raw, "summary", None),
            metrics=metrics,
            scenarios=list(getattr(raw, "scenarios", [])),
            risks=list(getattr(raw, "risks", [])),
            recommendations=list(getattr(raw, "recommendations", [])),
            artifacts=artifacts,
            correlation_id=correlation_id,
            engine_meta=EngineMeta(
                engine="agentsociety",
                engine_version=getattr(raw, "engine_version", None),
                adapter_version=adapter_version,
            ),
        )
