from __future__ import annotations

from typing import Any

_BOOKKEEPING_KEYS = {
    "projection_id",
    "content_hash",
    "expires_at",
    "anchor_at",
    "readiness_ref",
    "compliance_ref",
    "capital_ref",
    "reconciliation_ref",
    "health_ref",
    "created_at",
    "updated_at",
    "observed_at",
    "checked_at",
    "timestamp",
    "snapshot_id",
    "readiness_id",
    "compliance_id",
    "reconciliation_id",
    "report_id",
    "decision_id",
    "forecast_id",
    "recommendation_id",
    "trade_intent_id",
}


def execution_projection_signature(projection: Any | None) -> dict[str, Any] | None:
    if projection is None:
        return None

    model_dump = getattr(projection, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(mode="json")
    elif isinstance(projection, dict):
        payload = dict(projection)
    else:
        return None

    if not isinstance(payload, dict):
        return None
    return _strip_bookkeeping(payload)


def _strip_bookkeeping(payload: Any) -> Any:
    if isinstance(payload, dict):
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            if key in _BOOKKEEPING_KEYS:
                continue
            cleaned[key] = _strip_bookkeeping(value)
        return cleaned
    if isinstance(payload, list):
        return [_strip_bookkeeping(item) for item in payload]
    return payload
