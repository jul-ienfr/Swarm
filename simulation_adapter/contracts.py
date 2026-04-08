from __future__ import annotations

from runtime_contracts.adapter_command import AdapterCommand, AdapterCommandV1

from .adapter import CancelRunRequest, CreateRunRequest, GetResultRequest, GetStatusRequest


def command_to_request(command: AdapterCommandV1):
    payload = command.model_dump(mode="python")
    payload.pop("command", None)
    if command.command == AdapterCommand.create_run:
        return CreateRunRequest.model_validate(payload)
    if command.command == AdapterCommand.get_status:
        return GetStatusRequest.model_validate(payload)
    if command.command == AdapterCommand.get_result:
        return GetResultRequest.model_validate(payload)
    if command.command == AdapterCommand.cancel_run:
        return CancelRunRequest.model_validate(payload)
    raise ValueError(f"Unsupported adapter command: {command.command}")
