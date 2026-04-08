from __future__ import annotations

import json
import logging
from typing import Any


def log_structured_event(
    logger_name: str,
    level: str,
    event: str,
    **fields: Any,
) -> None:
    logger = logging.getLogger(logger_name)
    payload = {
        "event": event,
        **{key: value for key, value in fields.items() if value is not None},
    }
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.log(log_level, json.dumps(payload, sort_keys=True, default=str))
