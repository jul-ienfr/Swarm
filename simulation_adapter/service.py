from __future__ import annotations

import logging
from collections.abc import Callable

from observability import log_structured_event
from runtime_contracts.adapter_command import AdapterCommand, AdapterCommandV1, EngineTarget
from runtime_contracts.adapter_result import AdapterResultV1, EngineMeta, EngineErrorCode, NormalizedError, RunStatus

from .adapter import SimulationEngineAdapter
from .contracts import command_to_request
from .errors import AdapterError, EngineUnavailableError
from .mapping_store import RunMappingStore

SUPPORTED_ADAPTER_VERSION = "v1"

logger = logging.getLogger(__name__)


class AdapterService:
    def __init__(
        self,
        *,
        store: RunMappingStore,
        adapters: dict[EngineTarget, SimulationEngineAdapter] | None = None,
    ) -> None:
        self.store = store
        self.adapters = dict(adapters or {})

    def register_engine(self, engine: EngineTarget, adapter: SimulationEngineAdapter) -> None:
        self.adapters[engine] = adapter

    def dispatch(self, command: AdapterCommandV1) -> AdapterResultV1:
        if command.adapter_version != SUPPORTED_ADAPTER_VERSION:
            log_structured_event(
                "simulation_adapter.service",
                "warning",
                "adapter_version_mismatch",
                runtime_run_id=command.runtime_run_id,
                engine=command.engine.value,
                command=command.command.value,
                requested_adapter_version=command.adapter_version,
                supported_adapter_version=SUPPORTED_ADAPTER_VERSION,
                correlation_id=command.correlation_id,
            )
            result = self._error_result(
                runtime_run_id=command.runtime_run_id,
                engine=command.engine.value,
                correlation_id=command.correlation_id,
                error=NormalizedError.from_code(
                    EngineErrorCode.version_mismatch,
                    f"Unsupported adapter version: {command.adapter_version}",
                ),
            )
            self._sync_store_status(command.runtime_run_id, result.status)
            return result

        adapter = self.adapters.get(command.engine)
        if adapter is None:
            log_structured_event(
                "simulation_adapter.service",
                "warning",
                "engine_unavailable",
                runtime_run_id=command.runtime_run_id,
                engine=command.engine.value,
                command=command.command.value,
                correlation_id=command.correlation_id,
            )
            result = self._error_result(
                runtime_run_id=command.runtime_run_id,
                engine=command.engine.value,
                correlation_id=command.correlation_id,
                status=RunStatus.engine_unavailable,
                error=NormalizedError.from_code(
                    EngineErrorCode.engine_unavailable,
                    f"No adapter registered for engine '{command.engine.value}'.",
                    retryable=True,
                ),
            )
            self._sync_store_status(command.runtime_run_id, result.status)
            return result

        if command.command == AdapterCommand.create_run:
            self.store.create(
                command.swarm_intent_id or "",
                command.runtime_run_id,
                command.engine.value,
                command.correlation_id,
            )

        request = command_to_request(command)
        handler = self._resolve_handler(adapter, command.command)

        try:
            result = handler(request)
        except EngineUnavailableError as exc:
            logger.warning("Engine unavailable for %s: %s", command.engine.value, exc)
            log_structured_event(
                "simulation_adapter.service",
                "warning",
                "engine_unavailable",
                runtime_run_id=command.runtime_run_id,
                engine=command.engine.value,
                command=command.command.value,
                correlation_id=command.correlation_id,
                error_code=exc.code.value,
                status=exc.status.value,
                detail=exc.detail,
            )
            result = self._error_result(
                runtime_run_id=command.runtime_run_id,
                engine=command.engine.value,
                correlation_id=command.correlation_id,
                status=exc.status,
                error=exc.to_normalized_error(),
            )
            self._sync_store_status(command.runtime_run_id, result.status)
            return result
        except AdapterError as exc:
            logger.warning("Adapter error for %s: %s", command.engine.value, exc)
            log_structured_event(
                "simulation_adapter.service",
                "warning",
                "adapter_error",
                runtime_run_id=command.runtime_run_id,
                engine=command.engine.value,
                command=command.command.value,
                correlation_id=command.correlation_id,
                error_code=exc.code.value,
                status=exc.status.value,
                retryable=exc.retryable,
                detail=exc.detail,
            )
            result = self._error_result(
                runtime_run_id=command.runtime_run_id,
                engine=command.engine.value,
                correlation_id=command.correlation_id,
                status=exc.status,
                error=exc.to_normalized_error(),
            )
            self._sync_store_status(command.runtime_run_id, result.status)
            return result
        except Exception as exc:  # pragma: no cover - defensive guardrail
            logger.exception("Unexpected adapter failure for %s", command.engine.value)
            log_structured_event(
                "simulation_adapter.service",
                "error",
                "adapter_unexpected_failure",
                runtime_run_id=command.runtime_run_id,
                engine=command.engine.value,
                command=command.command.value,
                correlation_id=command.correlation_id,
                error=str(exc),
            )
            result = self._error_result(
                runtime_run_id=command.runtime_run_id,
                engine=command.engine.value,
                correlation_id=command.correlation_id,
                error=NormalizedError.from_code(
                    EngineErrorCode.unknown,
                    str(exc),
                    retryable=False,
                ),
            )
            self._sync_store_status(command.runtime_run_id, result.status)
            return result

        self._sync_store_status(command.runtime_run_id, result.status)
        log_structured_event(
            "simulation_adapter.service",
            "info",
            "adapter_dispatch_completed",
            runtime_run_id=command.runtime_run_id,
            engine=command.engine.value,
            command=command.command.value,
            correlation_id=command.correlation_id,
            status=result.status.value,
            engine_run_id=result.engine_run_id,
            error_codes=[error.error_code.value for error in result.errors],
        )
        return result

    @staticmethod
    def _resolve_handler(
        adapter: SimulationEngineAdapter,
        command: AdapterCommand,
    ) -> Callable:
        if command == AdapterCommand.create_run:
            return adapter.create_run
        if command == AdapterCommand.get_status:
            return adapter.get_status
        if command == AdapterCommand.get_result:
            return adapter.get_result
        if command == AdapterCommand.cancel_run:
            return adapter.cancel_run
        raise ValueError(f"Unsupported adapter command: {command}")

    @staticmethod
    def _error_result(
        *,
        runtime_run_id: str,
        engine: str,
        correlation_id: str | None,
        error: NormalizedError,
        status: RunStatus = RunStatus.failed,
    ) -> AdapterResultV1:
        return AdapterResultV1(
            runtime_run_id=runtime_run_id,
            status=status,
            engine_meta=EngineMeta(engine=engine, adapter_version=SUPPORTED_ADAPTER_VERSION),
            errors=[error],
            correlation_id=correlation_id,
        )

    def _sync_store_status(self, runtime_run_id: str, status: RunStatus) -> None:
        mapping = self.store.get_by_runtime_run_id(runtime_run_id)
        if mapping is not None:
            self.store.update_status(runtime_run_id, status)
