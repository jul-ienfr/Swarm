"""
Polls AgentSociety-native progress and maps it to normalized adapter status.
Raw engine status never leaves this module.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

from runtime_contracts.adapter_result import EngineErrorCode, ProgressInfo, RunStatus
from simulation_adapter.errors import AdapterError, EngineUnavailableError

logger = logging.getLogger(__name__)


class AgentSocietyMonitor:
    def __init__(self, engine_client, poll_interval: float = 5.0):
        self._client = engine_client
        self._poll_interval = poll_interval

    def poll(self, engine_run_id: str) -> tuple[RunStatus, ProgressInfo | None]:
        try:
            raw_status = self._client.get_run_status(engine_run_id)
            return self._map_status(raw_status), self._map_progress(raw_status)
        except Exception as exc:
            logger.exception("AgentSocietyMonitor.poll failed for %s", engine_run_id)
            if self._is_engine_unavailable(exc):
                raise EngineUnavailableError(engine="agentsociety", detail=str(exc)) from exc
            raise AdapterError(
                code=EngineErrorCode.transient_failure,
                message=str(exc),
                retryable=True,
            ) from exc

    def wait_for_terminal(
        self,
        engine_run_id: str,
        timeout_seconds: float = 1800,
        on_progress: Callable[[RunStatus, ProgressInfo | None], None] | None = None,
    ) -> tuple[RunStatus, ProgressInfo | None]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            status, progress = self.poll(engine_run_id)
            if on_progress:
                on_progress(status, progress)
            if status.is_terminal:
                return status, progress
            time.sleep(self._poll_interval)
        return RunStatus.timed_out, None

    @staticmethod
    def _map_status(raw) -> RunStatus:
        status_value = getattr(raw, "status", raw)
        mapping = {
            "PENDING": RunStatus.queued,
            "QUEUED": RunStatus.queued,
            "RUNNING": RunStatus.running,
            "DONE": RunStatus.completed,
            "COMPLETED": RunStatus.completed,
            "ERROR": RunStatus.failed,
            "FAILED": RunStatus.failed,
            "CANCELLED": RunStatus.cancelled,
            "TIMED_OUT": RunStatus.timed_out,
        }
        return mapping.get(str(status_value).upper(), RunStatus.failed)

    @staticmethod
    def _map_progress(raw) -> ProgressInfo | None:
        percent_complete = getattr(raw, "progress_pct", None)
        current_step = getattr(raw, "current_step", None)
        message = getattr(raw, "message", None)
        if percent_complete is None and current_step is None and message is None:
            return None
        return ProgressInfo(
            percent_complete=percent_complete,
            current_step=current_step,
            message=message,
        )

    @staticmethod
    def _is_engine_unavailable(exc: Exception) -> bool:
        return isinstance(exc, (ConnectionError, OSError, TimeoutError))
