from __future__ import annotations

from dataclasses import dataclass

from .adapters import PolymarketAdapter, VenueAdapter
from .market_graph import MarketGraphBuilder
from .models import LedgerPosition, MarketDescriptor, MarketStatus, MarketUniverseConfig, MarketUniverseResult, VenueName
from .registry import DEFAULT_VENUE_EXECUTION_REGISTRY


def _surface_route_refs(surface: dict[str, object]) -> dict[str, str]:
    route_refs: dict[str, str] = {}
    for route_key, source_key in (
        ("events", "events_source"),
        ("positions", "positions_source"),
        ("market_feed", "market_feed_source"),
        ("user_feed", "user_feed_source"),
    ):
        value = surface.get(source_key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text != "unavailable":
            route_refs[route_key] = text
    configured = surface.get("configured_endpoints")
    if isinstance(configured, dict):
        for key, value in configured.items():
            if value is None:
                continue
            text = str(value).strip()
            if text and text != "unavailable":
                route_refs.setdefault(str(key), text)
    return route_refs


def _is_live_transport_ready(*, supported: bool, route_ref: str | None, status: str) -> bool:
    return bool(supported and route_ref and status in {"configured_endpoint", "endpoint_configured"})


def _live_transport_operational_status(*, supported: bool, ready: bool) -> str:
    if ready:
        return "ready"
    return "not_supported" if not supported else "unavailable"


def _surface_availability_probes(surface: dict[str, object]) -> dict[str, object]:
    route_refs = dict(surface.get("route_refs") or _surface_route_refs(surface))
    market_feed_status = str(surface.get("market_feed_status", "unavailable"))
    market_feed_route = route_refs.get("market_feed")
    market_feed_cache_backed = bool(surface.get("market_feed_cache_backed", False))
    market_feed_probe_ready = market_feed_status in {
        "configured_endpoint",
        "endpoint_configured",
        "fixture_available",
        "surrogate_available",
        "local_cache",
    } and bool(market_feed_route)
    market_feed_operational_status = "ready" if market_feed_probe_ready else "unavailable"

    user_feed_status = str(surface.get("user_feed_status", "unavailable"))
    user_feed_route = route_refs.get("user_feed")
    user_feed_cache_backed = bool(surface.get("user_feed_cache_backed", False))
    user_feed_probe_ready = user_feed_status in {
        "configured_endpoint",
        "endpoint_configured",
        "fixture_available",
        "surrogate_available",
        "local_cache",
    } and bool(user_feed_route)
    user_feed_operational_status = "ready" if user_feed_probe_ready else "unavailable"

    websocket_market_supported = bool(surface.get("supports_websocket", False))
    websocket_market_status = str(surface.get("market_websocket_status", surface.get("websocket_status", "unavailable")))
    websocket_market_route = route_refs.get("market_websocket")
    websocket_market_probe_ready = _is_live_transport_ready(
        supported=websocket_market_supported,
        route_ref=websocket_market_route,
        status=websocket_market_status,
    )
    websocket_market_operational_status = _live_transport_operational_status(
        supported=websocket_market_supported,
        ready=websocket_market_probe_ready,
    )

    websocket_user_supported = bool(surface.get("supports_websocket", False))
    websocket_user_status = str(surface.get("user_feed_websocket_status", surface.get("websocket_status", "unavailable")))
    websocket_user_route = route_refs.get("user_websocket")
    websocket_user_probe_ready = _is_live_transport_ready(
        supported=websocket_user_supported,
        route_ref=websocket_user_route,
        status=websocket_user_status,
    )
    websocket_user_operational_status = _live_transport_operational_status(
        supported=websocket_user_supported,
        ready=websocket_user_probe_ready,
    )

    rtds_supported = bool(surface.get("supports_rtds", False))
    rtds_status = str(surface.get("rtds_status", "unavailable"))
    rtds_route = route_refs.get("rtds")
    rtds_cache_backed = bool(surface.get("rtds_cache_backed", False))
    rtds_probe_ready = _is_live_transport_ready(
        supported=rtds_supported,
        route_ref=rtds_route,
        status=rtds_status,
    )
    rtds_operational_status = _live_transport_operational_status(
        supported=rtds_supported,
        ready=rtds_probe_ready,
    )

    return {
        "market_feed": {
            "status": market_feed_status,
            "transport": str(surface.get("market_feed_transport", "unavailable")),
            "connector": str(surface.get("market_feed_connector", "unavailable")),
            "route_ref": market_feed_route,
            "replayable": bool(surface.get("market_feed_replayable", True)),
            "cache_backed": market_feed_cache_backed,
            "probe_ready": market_feed_probe_ready,
            "operational_status": market_feed_operational_status,
            "recommended_action": "use_cache_backed_snapshot" if market_feed_cache_backed else "poll_snapshot_route",
            "severity": "info" if market_feed_operational_status == "ready" else "error",
            "gap_reason": "snapshot_only_no_push" if market_feed_cache_backed else "poll_only_surface",
            "documented_route_ref": market_feed_route,
        },
        "user_feed": {
            "status": user_feed_status,
            "transport": str(surface.get("user_feed_transport", "unavailable")),
            "connector": str(surface.get("user_feed_connector", "unavailable")),
            "route_ref": user_feed_route,
            "replayable": bool(surface.get("user_feed_replayable", False)),
            "cache_backed": user_feed_cache_backed,
            "probe_ready": user_feed_probe_ready,
            "operational_status": user_feed_operational_status,
            "recommended_action": "read_user_feed_cache" if user_feed_cache_backed else "poll_snapshot_route",
            "severity": "info" if user_feed_operational_status == "ready" else "warning",
            "gap_reason": "user_feed_proxy_cache" if user_feed_cache_backed else "no_user_feed_binding",
            "documented_route_ref": user_feed_route,
        },
        "websocket_market": {
            "status": websocket_market_status,
            "transport": "websocket",
            "connector": "unavailable",
            "route_ref": websocket_market_route,
            "replayable": False,
            "cache_backed": False,
            "supported": websocket_market_supported,
            "probe_ready": websocket_market_probe_ready,
            "operational_status": websocket_market_operational_status,
            "recommended_action": "subscribe_websocket" if websocket_market_probe_ready else "do_not_assume_live_websocket",
            "severity": "info",
            "gap_reason": None if websocket_market_probe_ready else "live_websocket_not_bound",
            "documented_route_ref": websocket_market_route,
        },
        "websocket_user": {
            "status": websocket_user_status,
            "transport": "websocket",
            "connector": "unavailable",
            "route_ref": websocket_user_route,
            "replayable": False,
            "cache_backed": False,
            "supported": websocket_user_supported,
            "probe_ready": websocket_user_probe_ready,
            "operational_status": websocket_user_operational_status,
            "recommended_action": "subscribe_websocket" if websocket_user_probe_ready else "do_not_assume_live_websocket",
            "severity": "info",
            "gap_reason": None if websocket_user_probe_ready else "live_user_feed_not_bound",
            "documented_route_ref": websocket_user_route,
        },
        "rtds": {
            "status": rtds_status,
            "transport": "rtds",
            "connector": str(surface.get("rtds_connector", "unavailable")),
            "route_ref": rtds_route,
            "replayable": bool(surface.get("rtds_replayable", False)),
            "cache_backed": rtds_cache_backed,
            "supported": rtds_supported,
            "probe_ready": rtds_probe_ready,
            "operational_status": rtds_operational_status,
            "recommended_action": "subscribe_rtds" if rtds_probe_ready else "do_not_assume_rtds",
            "severity": "info",
            "gap_reason": None if rtds_probe_ready else "rtds_not_bound",
            "documented_route_ref": rtds_route,
        },
    }


def _surface_cache_fallbacks(surface: dict[str, object]) -> dict[str, object]:
    route_refs = dict(surface.get("route_refs") or _surface_route_refs(surface))
    return {
        "market_feed": {
            "status": "ready" if bool(surface.get("market_feed_cache_backed", False)) else "not_configured",
            "connector": str(surface.get("market_feed_connector", "unavailable")),
            "route_ref": route_refs.get("market_feed"),
            "replayable": bool(surface.get("market_feed_replayable", True)),
            "cache_backed": bool(surface.get("market_feed_cache_backed", False)),
            "operational_status": "ready" if bool(surface.get("market_feed_cache_backed", False)) else "not_configured",
            "recommended_action": "use_cache_fallback" if bool(surface.get("market_feed_cache_backed", False)) else "no_cache_fallback",
        },
        "user_feed": {
            "status": "ready" if bool(surface.get("user_feed_cache_backed", False)) else "not_configured",
            "connector": str(surface.get("user_feed_connector", "unavailable")),
            "route_ref": route_refs.get("user_feed"),
            "replayable": bool(surface.get("user_feed_replayable", False)),
            "cache_backed": bool(surface.get("user_feed_cache_backed", False)),
            "operational_status": "ready" if bool(surface.get("user_feed_cache_backed", False)) else "not_configured",
            "recommended_action": "use_cache_fallback" if bool(surface.get("user_feed_cache_backed", False)) else "no_cache_fallback",
        },
        "rtds": {
            "status": "ready" if bool(surface.get("rtds_cache_backed", False)) else "not_configured",
            "connector": str(surface.get("rtds_connector", "unavailable")),
            "route_ref": route_refs.get("rtds"),
            "replayable": bool(surface.get("rtds_replayable", False)),
            "cache_backed": bool(surface.get("rtds_cache_backed", False)),
            "operational_status": "ready" if bool(surface.get("rtds_cache_backed", False)) else "not_configured",
            "recommended_action": "use_cache_fallback" if bool(surface.get("rtds_cache_backed", False)) else "no_cache_fallback",
        },
    }


def _surface_connector_contracts(surface: dict[str, object]) -> dict[str, object]:
    route_refs = dict(surface.get("route_refs") or _surface_route_refs(surface))
    probes = dict(surface.get("availability_probes") or _surface_availability_probes(surface))
    websocket_market_ready = dict(probes.get("websocket_market") or {}).get("operational_status") == "ready"
    websocket_user_ready = dict(probes.get("websocket_user") or {}).get("operational_status") == "ready"
    rtds_ready = dict(probes.get("rtds") or {}).get("operational_status") == "ready"
    return {
        "market_feed": {
            "mode": "read_only",
            "transport": str(surface.get("market_feed_transport", "unavailable")),
            "connector": str(surface.get("market_feed_connector", "unavailable")),
            "route_ref": route_refs.get("market_feed"),
            "kind": str(surface.get("market_feed_kind", "market_snapshot")),
            "supports_live": False,
            "supports_write": False,
            "subscription_capable": False,
            "replayable": bool(surface.get("market_feed_replayable", True)),
            "cache_backed": bool(surface.get("market_feed_cache_backed", False)),
            "readiness": dict(probes.get("market_feed") or {}).get("operational_status", "unavailable"),
            "auth_requirement": "none",
            "session_requirement": "none",
            "endpoint_contract": {
                "method": "GET",
                "route_ref": route_refs.get("market_feed"),
                "request_mode": "pull",
                "response_kind": "market_snapshot",
                "read_only": True,
                "write_capable": False,
            },
        },
        "user_feed": {
            "mode": "read_only",
            "transport": str(surface.get("user_feed_transport", "unavailable")),
            "connector": str(surface.get("user_feed_connector", "unavailable")),
            "route_ref": route_refs.get("user_feed"),
            "kind": str(surface.get("user_feed_kind", "position_snapshot")),
            "supports_live": False,
            "supports_write": False,
            "subscription_capable": False,
            "replayable": bool(surface.get("user_feed_replayable", False)),
            "cache_backed": bool(surface.get("user_feed_cache_backed", False)),
            "readiness": dict(probes.get("user_feed") or {}).get("operational_status", "unavailable"),
            "auth_requirement": "none",
            "session_requirement": "local_cache_context" if bool(surface.get("user_feed_cache_backed", False)) else "none",
            "endpoint_contract": {
                "method": "GET",
                "route_ref": route_refs.get("user_feed"),
                "request_mode": "pull",
                "response_kind": "position_snapshot",
                "read_only": True,
                "write_capable": False,
            },
        },
        "websocket_market": {
            "mode": "live_bound" if websocket_market_ready else "preview_only",
            "transport": "websocket",
            "connector": str(surface.get("market_websocket_connector", route_refs.get("market_websocket", "unavailable"))),
            "route_ref": route_refs.get("market_websocket"),
            "kind": "market_stream",
            "supports_live": websocket_market_ready,
            "supports_write": False,
            "subscription_capable": websocket_market_ready,
            "replayable": False,
            "cache_backed": False,
            "readiness": dict(probes.get("websocket_market") or {}).get("operational_status", "not_supported"),
            "auth_requirement": "operator_bound" if websocket_market_ready else "not_bound",
            "session_requirement": "live_session" if websocket_market_ready else "preview_only",
            "endpoint_contract": {
                "method": "CONNECT" if websocket_market_ready else "PREVIEW_ONLY",
                "route_ref": route_refs.get("market_websocket"),
                "request_mode": "live_subscription" if websocket_market_ready else "preview_only",
                "response_kind": "market_stream" if websocket_market_ready else "market_stream_preview",
                "read_only": True,
                "write_capable": False,
            },
        },
        "websocket_user": {
            "mode": "live_bound" if websocket_user_ready else "preview_only",
            "transport": "websocket",
            "connector": str(surface.get("user_websocket_connector", route_refs.get("user_websocket", "unavailable"))),
            "route_ref": route_refs.get("user_websocket"),
            "kind": "user_stream",
            "supports_live": websocket_user_ready,
            "supports_write": False,
            "subscription_capable": websocket_user_ready,
            "replayable": False,
            "cache_backed": False,
            "readiness": dict(probes.get("websocket_user") or {}).get("operational_status", "not_supported"),
            "auth_requirement": "operator_bound" if websocket_user_ready else "not_bound",
            "session_requirement": "live_session" if websocket_user_ready else "preview_only",
            "endpoint_contract": {
                "method": "CONNECT" if websocket_user_ready else "PREVIEW_ONLY",
                "route_ref": route_refs.get("user_websocket"),
                "request_mode": "live_subscription" if websocket_user_ready else "preview_only",
                "response_kind": "user_stream" if websocket_user_ready else "user_stream_preview",
                "read_only": True,
                "write_capable": False,
            },
        },
        "rtds": {
            "mode": "live_bound" if rtds_ready else "preview_only",
            "transport": "rtds",
            "connector": str(surface.get("rtds_connector", "unavailable")),
            "route_ref": route_refs.get("rtds"),
            "kind": "rtds",
            "supports_live": rtds_ready,
            "supports_write": False,
            "subscription_capable": rtds_ready,
            "replayable": bool(surface.get("rtds_replayable", False)),
            "cache_backed": bool(surface.get("rtds_cache_backed", False)),
            "readiness": dict(probes.get("rtds") or {}).get("operational_status", "not_supported"),
            "auth_requirement": "operator_bound" if rtds_ready else "not_bound",
            "session_requirement": "live_session" if rtds_ready else "preview_only",
            "endpoint_contract": {
                "method": "CONNECT" if rtds_ready else "PREVIEW_ONLY",
                "route_ref": route_refs.get("rtds"),
                "request_mode": "live_subscription" if rtds_ready else "preview_only",
                "response_kind": "rtds" if rtds_ready else "rtds_preview",
                "read_only": True,
                "write_capable": False,
            },
        },
        "documented_routes": {
            "market_feed": route_refs.get("market_feed"),
            "user_feed": route_refs.get("user_feed"),
            "market_websocket": route_refs.get("market_websocket"),
            "user_websocket": route_refs.get("user_websocket"),
            "rtds": route_refs.get("rtds"),
        },
        "auth_requirements": {
            "market_feed": "none",
            "user_feed": "none",
            "websocket_market": "operator_bound" if websocket_market_ready else "not_bound",
            "websocket_user": "operator_bound" if websocket_user_ready else "not_bound",
            "rtds": "operator_bound" if rtds_ready else "not_bound",
        },
        "session_requirements": {
            "market_feed": "none",
            "user_feed": "local_cache_context" if bool(surface.get("user_feed_cache_backed", False)) else "none",
            "websocket_market": "live_session" if websocket_market_ready else "preview_only",
            "websocket_user": "live_session" if websocket_user_ready else "preview_only",
            "rtds": "live_session" if rtds_ready else "preview_only",
        },
        "explicit_gaps": [
            "market_feed_is_snapshot_only",
            "user_feed_is_cache_proxy" if bool(surface.get("user_feed_cache_backed", False)) else "user_feed_not_bound",
            *[
                gap
                for gap, ready in (
                    ("websocket_market_not_bound", websocket_market_ready),
                    ("websocket_user_not_bound", websocket_user_ready),
                    ("rtds_not_bound", rtds_ready),
                )
                if not ready
            ],
        ],
        "replay_fallbacks": {
            "market_feed": "cache_fallback" if bool(surface.get("market_feed_cache_backed", False)) else "poll_snapshot_route",
            "user_feed": "cache_fallback" if bool(surface.get("user_feed_cache_backed", False)) else "poll_snapshot_route",
            "websocket_market": "no_live_binding",
            "websocket_user": "no_live_binding",
            "rtds": "no_live_binding",
        },
    }


def _surface_gap_summary(surface: dict[str, object]) -> dict[str, object]:
    probes = dict(surface.get("availability_probes") or _surface_availability_probes(surface))
    contracts = dict(surface.get("connector_contracts") or _surface_connector_contracts(surface))
    route_refs = dict(surface.get("route_refs") or _surface_route_refs(surface))
    channel_specs = dict(surface.get("channel_specs") or {})
    preview = dict(surface.get("subscription_preview") or {})
    preview_channels = dict(preview.get("channels") or {})
    if not preview_channels:
        preview_channels = {
            key: value
            for key, value in channel_specs.items()
            if str(dict(value or {}).get("delivery_mode", "")).strip() == "preview_only"
        }
    websocket_market_ready = dict(probes.get("websocket_market") or {}).get("operational_status") == "ready"
    websocket_user_ready = dict(probes.get("websocket_user") or {}).get("operational_status") == "ready"
    rtds_ready = dict(probes.get("rtds") or {}).get("operational_status") == "ready"
    return {
        "live_transport_supported": bool(surface.get("supports_websocket", False) or surface.get("supports_rtds", False)),
        "live_transport_ready_count": sum(
            1 for key in ("websocket_market", "websocket_user", "rtds") if dict(probes.get(key) or {}).get("operational_status") == "ready"
        ),
        "live_transport_not_supported_count": sum(
            1 for key in ("websocket_market", "websocket_user", "rtds") if dict(probes.get(key) or {}).get("operational_status") == "not_supported"
        ),
        "preview_only_channel_count": sum(
            1
            for channel in preview_channels.values()
            if str(dict(dict(channel or {}).get("channel_spec") or {}).get("delivery_mode", "")).strip() == "preview_only"
        ),
        "cache_backed_channel_count": sum(
            1 for key in ("market_feed", "user_feed") if bool(dict(probes.get(key) or {}).get("cache_backed", False))
        ),
        "documented_preview_routes": {
            "market_feed": route_refs.get("market_feed"),
            "user_feed": route_refs.get("user_feed"),
            "market_websocket": route_refs.get("market_websocket"),
            "user_websocket": route_refs.get("user_websocket"),
            "rtds": route_refs.get("rtds"),
        },
        "auth_requirements": dict(contracts.get("auth_requirements") or {}),
        "session_requirements": dict(contracts.get("session_requirements") or {}),
        "live_transport_gap_reasons": {
            key: dict(probes.get(key) or {}).get("gap_reason")
            for key in ("websocket_market", "websocket_user", "rtds")
        },
        "cache_backed_gap_reasons": {
            key: dict(probes.get(key) or {}).get("gap_reason")
            for key in ("market_feed", "user_feed")
        },
        "explicit_gaps": list(
            surface.get("explicit_gaps")
            or [
                dict(spec or {}).get("explicit_gap")
                for spec in channel_specs.values()
                if dict(spec or {}).get("explicit_gap")
            ]
        ),
    }


def _surface_preview_flow(surface: dict[str, object]) -> dict[str, object]:
    route_refs = dict(surface.get("route_refs") or _surface_route_refs(surface))
    probes = dict(surface.get("availability_probes") or _surface_availability_probes(surface))
    contracts = dict(surface.get("connector_contracts") or {})
    venue_obj = surface.get("venue")
    venue_name = venue_obj.value if isinstance(venue_obj, VenueName) else str(venue_obj or "venue")
    websocket_market_ready = dict(probes.get("websocket_market") or {}).get("operational_status") == "ready"
    websocket_user_ready = dict(probes.get("websocket_user") or {}).get("operational_status") == "ready"
    rtds_ready = dict(probes.get("rtds") or {}).get("operational_status") == "ready"
    live_transport_ready = websocket_market_ready or websocket_user_ready or rtds_ready
    return {
        "flow_id": f"{venue_name}:bounded_websocket_rtds_preview",
        "mode": "live_bound" if live_transport_ready else "preview_only",
        "testable": True,
        "live_claimed": live_transport_ready,
        "route_refs": {
            "market_feed": route_refs.get("market_feed"),
            "user_feed": route_refs.get("user_feed"),
            "market_websocket": route_refs.get("market_websocket"),
            "user_websocket": route_refs.get("user_websocket"),
            "rtds": route_refs.get("rtds"),
        },
        "steps": [
            {
                "step": "resolve_routes",
                "status": "complete",
                "documented_route_refs": {
                    "market_feed": route_refs.get("market_feed"),
                    "user_feed": route_refs.get("user_feed"),
                    "market_websocket": route_refs.get("market_websocket"),
                    "user_websocket": route_refs.get("user_websocket"),
                    "rtds": route_refs.get("rtds"),
                },
            },
            {
                "step": "confirm_auth_and_session",
                "status": "complete",
                "auth_requirements": dict(contracts.get("auth_requirements") or {}),
                "session_requirements": dict(contracts.get("session_requirements") or {}),
            },
            {
                "step": "select_preview_fallbacks",
                "status": "complete",
                "preview_targets": {
                    "market_feed": dict(probes.get("market_feed") or {}).get("recommended_action", "poll_snapshot_route"),
                    "user_feed": dict(probes.get("user_feed") or {}).get("recommended_action", "treat_as_unavailable"),
                    "websocket_market": dict(probes.get("websocket_market") or {}).get("recommended_action", "do_not_assume_live_websocket"),
                    "websocket_user": dict(probes.get("websocket_user") or {}).get("recommended_action", "do_not_assume_live_websocket"),
                    "rtds": dict(probes.get("rtds") or {}).get("recommended_action", "do_not_assume_rtds"),
                },
            },
        ],
        "bounded_channels": ["websocket_market", "websocket_user", "rtds"],
        "preview_only_channels": [
            key
            for key, ready in (
                ("websocket_market", websocket_market_ready),
                ("websocket_user", websocket_user_ready),
                ("rtds", rtds_ready),
            )
            if not ready
        ],
        "probe_statuses": {
            "websocket_market": dict(probes.get("websocket_market") or {}).get("operational_status", "not_supported"),
            "websocket_user": dict(probes.get("websocket_user") or {}).get("operational_status", "not_supported"),
            "rtds": dict(probes.get("rtds") or {}).get("operational_status", "not_supported"),
        },
        "expected_outcome": "live_transport_available" if live_transport_ready else "preview_only_no_live_transport",
    }


def _surface_subscription_preview(surface: dict[str, object]) -> dict[str, object]:
    route_refs = dict(surface.get("route_refs") or _surface_route_refs(surface))
    probes = dict(surface.get("availability_probes") or _surface_availability_probes(surface))
    venue_name = str(surface.get("venue", "venue"))
    contracts = dict(surface.get("connector_contracts") or {})
    preview_flow = _surface_preview_flow(surface)
    websocket_market_ready = dict(probes.get("websocket_market") or {}).get("operational_status") == "ready"
    websocket_user_ready = dict(probes.get("websocket_user") or {}).get("operational_status") == "ready"
    rtds_ready = dict(probes.get("rtds") or {}).get("operational_status") == "ready"
    live_transport_ready = websocket_market_ready or websocket_user_ready or rtds_ready
    gap_summary = {
        "live_transport_supported": bool(surface.get("supports_websocket", False) or surface.get("supports_rtds", False)),
        "live_transport_ready_count": sum(
            1 for key in ("websocket_market", "websocket_user", "rtds") if dict(probes.get(key) or {}).get("operational_status") == "ready"
        ),
        "live_transport_not_supported_count": sum(
            1 for key in ("websocket_market", "websocket_user", "rtds") if dict(probes.get(key) or {}).get("operational_status") == "not_supported"
        ),
        "preview_only_channel_count": sum(1 for ready in (websocket_market_ready, websocket_user_ready, rtds_ready) if not ready),
        "cache_backed_channel_count": sum(
            1 for key in ("market_feed", "user_feed") if bool(dict(probes.get(key) or {}).get("cache_backed", False))
        ),
        "documented_preview_routes": {
            "market_feed": route_refs.get("market_feed"),
            "user_feed": route_refs.get("user_feed"),
            "market_websocket": route_refs.get("market_websocket"),
            "user_websocket": route_refs.get("user_websocket"),
            "rtds": route_refs.get("rtds"),
        },
        "auth_requirements": dict(contracts.get("auth_requirements") or {}),
        "session_requirements": dict(contracts.get("session_requirements") or {}),
        "live_transport_gap_reasons": {
            key: dict(probes.get(key) or {}).get("gap_reason")
            for key in ("websocket_market", "websocket_user", "rtds")
        },
        "cache_backed_gap_reasons": {
            key: dict(probes.get(key) or {}).get("gap_reason")
            for key in ("market_feed", "user_feed")
        },
        "explicit_gaps": [
            "market_feed_is_snapshot_only",
            "user_feed_is_cache_proxy" if bool(dict(probes.get("user_feed") or {}).get("cache_backed", False)) else "user_feed_not_bound",
            *[
                gap
                for gap, ready in (
                    ("websocket_market_not_bound", websocket_market_ready),
                    ("websocket_user_not_bound", websocket_user_ready),
                    ("rtds_not_bound", rtds_ready),
                )
                if not ready
            ],
        ],
    }
    return {
        "mode": "live_bound" if live_transport_ready else "preview_only",
        "supports_live_subscriptions": live_transport_ready,
        "recommended_poll_transport": str(surface.get("market_feed_transport", "unavailable")),
        "recommended_user_transport": str(surface.get("user_feed_transport", "unavailable")),
        "auth_requirements": dict(contracts.get("auth_requirements") or {}),
        "session_requirements": dict(contracts.get("session_requirements") or {}),
        "channels": {
            "market_feed": {
                "topic": f"{venue_name}:market_feed",
                "route_ref": route_refs.get("market_feed"),
                "status": dict(probes.get("market_feed") or {}).get("operational_status", "unavailable"),
                "subscription_capable": False,
                "recommended_action": dict(probes.get("market_feed") or {}).get("recommended_action", "poll_snapshot_route"),
                "subscription_intent": "poll_snapshot",
                "auth_requirement": "none",
                "channel_spec": {
                    "delivery_mode": "pull",
                    "message_kind": "market_snapshot",
                    "cadence_hint": "poll_on_schedule",
                },
            },
            "user_feed": {
                "topic": f"{venue_name}:user_feed",
                "route_ref": route_refs.get("user_feed"),
                "status": dict(probes.get("user_feed") or {}).get("operational_status", "unavailable"),
                "subscription_capable": False,
                "recommended_action": dict(probes.get("user_feed") or {}).get("recommended_action", "treat_as_unavailable"),
                "subscription_intent": "read_cache" if dict(probes.get("user_feed") or {}).get("cache_backed") else "poll_snapshot",
                "auth_requirement": "none",
                "channel_spec": {
                    "delivery_mode": "pull",
                    "message_kind": "position_snapshot",
                    "cadence_hint": "poll_or_cache_read",
                },
            },
            "websocket_market": {
                "topic": f"{venue_name}:websocket_market",
                "route_ref": route_refs.get("market_websocket"),
                "status": dict(probes.get("websocket_market") or {}).get("operational_status", "not_supported"),
                "subscription_capable": websocket_market_ready,
                "recommended_action": "subscribe_websocket" if websocket_market_ready else "do_not_assume_live_websocket",
                "subscription_intent": "subscribe" if websocket_market_ready else "preview_only",
                "auth_requirement": "operator_bound" if websocket_market_ready else "not_bound",
                "channel_spec": {
                    "delivery_mode": "live" if websocket_market_ready else "preview_only",
                    "message_kind": "market_stream" if websocket_market_ready else "market_stream_preview",
                    "cadence_hint": "push" if websocket_market_ready else "none",
                },
            },
            "websocket_user": {
                "topic": f"{venue_name}:websocket_user",
                "route_ref": route_refs.get("user_websocket"),
                "status": dict(probes.get("websocket_user") or {}).get("operational_status", "not_supported"),
                "subscription_capable": websocket_user_ready,
                "recommended_action": "subscribe_websocket" if websocket_user_ready else "do_not_assume_live_websocket",
                "subscription_intent": "subscribe" if websocket_user_ready else "preview_only",
                "auth_requirement": "operator_bound" if websocket_user_ready else "not_bound",
                "channel_spec": {
                    "delivery_mode": "live" if websocket_user_ready else "preview_only",
                    "message_kind": "user_stream" if websocket_user_ready else "user_stream_preview",
                    "cadence_hint": "push" if websocket_user_ready else "none",
                },
            },
            "rtds": {
                "topic": f"{venue_name}:rtds",
                "route_ref": route_refs.get("rtds"),
                "status": dict(probes.get("rtds") or {}).get("operational_status", "not_supported"),
                "subscription_capable": rtds_ready,
                "recommended_action": "subscribe_rtds" if rtds_ready else "do_not_assume_rtds",
                "subscription_intent": "subscribe" if rtds_ready else "preview_only",
                "auth_requirement": "operator_bound" if rtds_ready else "not_bound",
                "channel_spec": {
                    "delivery_mode": "live" if rtds_ready else "preview_only",
                    "message_kind": "rtds" if rtds_ready else "rtds_preview",
                    "cadence_hint": "push" if rtds_ready else "none",
                },
            },
        },
        "channel_specs": {
            "market_feed": {
                "route_ref": route_refs.get("market_feed"),
                "delivery_mode": "pull",
                "message_kind": "market_snapshot",
                "auth_requirement": "none",
                "session_requirement": "none",
                "subscription_intent": "poll_snapshot",
                "preview_probe": dict(probes.get("market_feed") or {}),
                "replay_fallback": dict((surface.get("cache_fallbacks") or {}).get("market_feed") or {}),
                "explicit_gap": "snapshot_only_no_push",
            },
            "user_feed": {
                "route_ref": route_refs.get("user_feed"),
                "delivery_mode": "pull",
                "message_kind": "position_snapshot",
                "auth_requirement": "none",
                "session_requirement": "local_cache_context" if bool(contracts.get("user_feed", {}).get("cache_backed", False)) else "none",
                "subscription_intent": "read_cache" if dict(probes.get("user_feed") or {}).get("cache_backed") else "poll_snapshot",
                "preview_probe": dict(probes.get("user_feed") or {}),
                "replay_fallback": dict((surface.get("cache_fallbacks") or {}).get("user_feed") or {}),
                "explicit_gap": "user_feed_proxy_cache" if dict(probes.get("user_feed") or {}).get("cache_backed") else "no_user_feed_binding",
            },
            "websocket_market": {
                "route_ref": route_refs.get("market_websocket"),
                "delivery_mode": "live" if websocket_market_ready else "preview_only",
                "message_kind": "market_stream" if websocket_market_ready else "market_stream_preview",
                "auth_requirement": "operator_bound" if websocket_market_ready else "not_bound",
                "session_requirement": "live_session" if websocket_market_ready else "preview_only",
                "subscription_intent": "subscribe" if websocket_market_ready else "preview_only",
                "preview_probe": dict(probes.get("websocket_market") or {}),
                "replay_fallback": "no_live_binding",
                "explicit_gap": None if websocket_market_ready else "live_websocket_not_bound",
            },
            "websocket_user": {
                "route_ref": route_refs.get("user_websocket"),
                "delivery_mode": "live" if websocket_user_ready else "preview_only",
                "message_kind": "user_stream" if websocket_user_ready else "user_stream_preview",
                "auth_requirement": "operator_bound" if websocket_user_ready else "not_bound",
                "session_requirement": "live_session" if websocket_user_ready else "preview_only",
                "subscription_intent": "subscribe" if websocket_user_ready else "preview_only",
                "preview_probe": dict(probes.get("websocket_user") or {}),
                "replay_fallback": "no_live_binding",
                "explicit_gap": None if websocket_user_ready else "live_user_feed_not_bound",
            },
            "rtds": {
                "route_ref": route_refs.get("rtds"),
                "delivery_mode": "live" if rtds_ready else "preview_only",
                "message_kind": "rtds" if rtds_ready else "rtds_preview",
                "auth_requirement": "operator_bound" if rtds_ready else "not_bound",
                "session_requirement": "live_session" if rtds_ready else "preview_only",
                "subscription_intent": "subscribe" if rtds_ready else "preview_only",
                "preview_probe": dict(probes.get("rtds") or {}),
                "replay_fallback": "no_live_binding",
                "explicit_gap": None if rtds_ready else "rtds_not_bound",
            },
        },
        "subscription_bundles": {
            "poll_snapshot_bundle": {
                "bundle_id": f"{venue_name}:poll_snapshot_bundle",
                "channels": ["market_feed", "user_feed"],
                "route_refs": {
                    "market_feed": route_refs.get("market_feed"),
                    "user_feed": route_refs.get("user_feed"),
                },
                "auth_requirement": "none",
                "session_requirement": "local_cache_context" if bool(contracts.get("user_feed", {}).get("cache_backed", False)) else "none",
                "preview_only": False,
                "testable": True,
            },
            "websocket_preview_bundle": {
                "bundle_id": f"{venue_name}:websocket_preview_bundle",
                "channels": ["websocket_market", "websocket_user"],
                "route_refs": {
                    "market_websocket": route_refs.get("market_websocket"),
                    "user_websocket": route_refs.get("user_websocket"),
                },
                "auth_requirement": "operator_bound" if (websocket_market_ready or websocket_user_ready) else "not_bound",
                "session_requirement": "live_session" if (websocket_market_ready or websocket_user_ready) else "preview_only",
                "preview_only": not (websocket_market_ready or websocket_user_ready),
                "testable": True,
            },
            "rtds_preview_bundle": {
                "bundle_id": f"{venue_name}:rtds_preview_bundle",
                "channels": ["rtds"],
                "route_refs": {"rtds": route_refs.get("rtds")},
                "auth_requirement": "operator_bound" if rtds_ready else "not_bound",
                "session_requirement": "live_session" if rtds_ready else "preview_only",
                "preview_only": not rtds_ready,
                "testable": True,
            },
        },
        "preview_flow": preview_flow,
        "auth_required_any": live_transport_ready,
        "channel_count": 5,
        "recommended_subscriptions": [
            {
                "channel": "market_feed",
                "intent": "poll_snapshot",
                "route_ref": route_refs.get("market_feed"),
                "recommended_action": dict(probes.get("market_feed") or {}).get("recommended_action", "poll_snapshot_route"),
            },
            {
                "channel": "user_feed",
                "intent": "read_cache" if dict(probes.get("user_feed") or {}).get("cache_backed") else "poll_snapshot",
                "route_ref": route_refs.get("user_feed"),
                "recommended_action": dict(probes.get("user_feed") or {}).get("recommended_action", "treat_as_unavailable"),
            },
        ],
        "documented_channel_route_refs": {
            "market_feed": route_refs.get("market_feed"),
            "user_feed": route_refs.get("user_feed"),
            "websocket_market": route_refs.get("market_websocket"),
            "websocket_user": route_refs.get("user_websocket"),
            "rtds": route_refs.get("rtds"),
        },
        "gap_summary": gap_summary,
        "explicit_gaps": [
            "market_feed_is_snapshot_only",
            "user_feed_is_cache_proxy" if dict(probes.get("user_feed") or {}).get("cache_backed") else "user_feed_not_bound",
            "websocket_market_not_bound",
            "websocket_user_not_bound",
            "rtds_not_bound",
        ],
        "replay_fallbacks": {
            "market_feed": dict((surface.get("cache_fallbacks") or {}).get("market_feed") or {}),
            "user_feed": dict((surface.get("cache_fallbacks") or {}).get("user_feed") or {}),
            "websocket_market": "no_live_binding",
            "websocket_user": "no_live_binding",
            "rtds": "no_live_binding",
        },
    }


def _surface_probe_bundle(surface: dict[str, object]) -> dict[str, object]:
    probes = dict(surface.get("availability_probes") or _surface_availability_probes(surface))
    cache_fallbacks = dict(surface.get("cache_fallbacks") or _surface_cache_fallbacks(surface))
    preview_flow = dict((surface.get("subscription_preview") or {}).get("preview_flow") or _surface_preview_flow(surface))
    operational_statuses = [str(dict(probe or {}).get("operational_status", "unavailable")) for probe in probes.values()]
    severity_counts = {"info": 0, "warning": 0, "error": 0}
    for probe in probes.values():
        severity = str(dict(probe or {}).get("severity", "info"))
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
    ready_count = sum(status == "ready" for status in operational_statuses)
    not_supported_count = sum(status == "not_supported" for status in operational_statuses)
    unavailable_count = sum(status == "unavailable" for status in operational_statuses)
    return {
        "bundle_status": "ready" if ready_count else "degraded",
        "probe_count": len(probes),
        "ready_count": ready_count,
        "not_supported_count": not_supported_count,
        "unavailable_count": unavailable_count,
        "primary_path": dict(probes.get("market_feed") or {}).get("recommended_action", "poll_snapshot_route"),
        "fallback_path": dict(cache_fallbacks.get("market_feed") or {}).get("recommended_action", "no_cache_fallback"),
        "market_feed_status": dict(probes.get("market_feed") or {}).get("operational_status", "unavailable"),
        "user_feed_status": dict(probes.get("user_feed") or {}).get("operational_status", "unavailable"),
        "transport_readiness": {
            key: dict(probe or {}).get("operational_status", "unavailable")
            for key, probe in probes.items()
        },
        "degraded_paths": [
            key
            for key, probe in probes.items()
            if dict(probe or {}).get("operational_status", "unavailable") != "ready"
        ],
        "preview_flow": preview_flow,
        "gap_summary": _surface_gap_summary(surface),
        "recovered_from_partial_probes": bool(surface.get("recovered_from_partial_probes", False)),
        "severity_counts": severity_counts,
        "highest_severity": "error" if severity_counts.get("error") else ("warning" if severity_counts.get("warning") else "info"),
    }


def _surface_capability_summary(surface: dict[str, object]) -> dict[str, object]:
    probes = dict(surface.get("availability_probes") or _surface_availability_probes(surface))
    preview_flow = dict((surface.get("subscription_preview") or {}).get("preview_flow") or _surface_preview_flow(surface))
    websocket_market_ready = dict(probes.get("websocket_market") or {}).get("operational_status") == "ready"
    websocket_user_ready = dict(probes.get("websocket_user") or {}).get("operational_status") == "ready"
    rtds_ready = dict(probes.get("rtds") or {}).get("operational_status") == "ready"
    live_transport_ready = websocket_market_ready or websocket_user_ready or rtds_ready
    return {
        "mode": "live_bound" if live_transport_ready else "read_only",
        "live_claimed": live_transport_ready,
        "subscription_mode": "live" if live_transport_ready else "preview_only",
        "market_feed_path": dict(probes.get("market_feed") or {}).get("recommended_action", "poll_snapshot_route"),
        "user_feed_path": dict(probes.get("user_feed") or {}).get("recommended_action", "treat_as_unavailable"),
        "websocket_path": dict(probes.get("websocket_market") or {}).get("recommended_action", "do_not_assume_live_websocket"),
        "rtds_path": dict(probes.get("rtds") or {}).get("recommended_action", "do_not_assume_rtds"),
        "has_replayable_market_feed": bool(surface.get("market_feed_replayable", True)),
        "has_cache_fallback": bool(surface.get("market_feed_cache_backed", False) or surface.get("user_feed_cache_backed", False)),
        "auth_requirements": {
            "market_feed": "none",
            "user_feed": "none",
            "websocket_market": "operator_bound" if websocket_market_ready else "not_bound",
            "websocket_user": "operator_bound" if websocket_user_ready else "not_bound",
            "rtds": "operator_bound" if rtds_ready else "not_bound",
        },
        "market_user_gap_reasons": [
            "market_feed_is_snapshot_only",
            "user_feed_is_cache_proxy" if bool(surface.get("user_feed_cache_backed", False)) else "user_feed_not_bound",
        ],
        "explicit_gaps": [
            gap
            for gap, ready in (
                ("websocket_market_not_bound", websocket_market_ready),
                ("websocket_user_not_bound", websocket_user_ready),
                ("rtds_not_bound", rtds_ready),
            )
            if not ready
        ],
        "rtds_usefulness": {
            "status": "live" if rtds_ready else "preview_only",
            "usable_for_live_ops": rtds_ready,
            "recommended_action": dict(probes.get("rtds") or {}).get("recommended_action", "do_not_assume_rtds"),
        },
        "recommended_subscriptions": [
            "market_feed",
            "user_feed",
            *[key for key, ready in (("websocket_market", websocket_market_ready), ("websocket_user", websocket_user_ready), ("rtds", rtds_ready)) if ready],
        ],
        "documented_preview_routes": {
            "market_websocket": dict(surface.get("route_refs") or {}).get("market_websocket"),
            "user_websocket": dict(surface.get("route_refs") or {}).get("user_websocket"),
            "rtds": dict(surface.get("route_refs") or {}).get("rtds"),
        },
        "gap_summary": _surface_gap_summary(surface),
        "preview_flow": preview_flow,
    }


@dataclass
class MarketUniverse:
    adapter: VenueAdapter | None = None

    def __post_init__(self) -> None:
        if self.adapter is None:
            self.adapter = PolymarketAdapter()

    def discover(self, config: MarketUniverseConfig | None = None) -> MarketUniverseResult:
        selected = config or MarketUniverseConfig(venue=VenueName.polymarket)
        markets = list(self.adapter.list_markets(config=selected, limit=selected.limit))
        input_count = len(markets)
        filtered_out: list[MarketDescriptor] = []
        if selected.active_only:
            kept: list[MarketDescriptor] = []
            for market in markets:
                if market.status in {MarketStatus.open, MarketStatus.resolved}:
                    kept.append(market)
                else:
                    filtered_out.append(market)
            markets = kept
        before_liquidity_filter = len(markets)
        markets = [market for market in markets if market.liquidity is None or market.liquidity >= selected.min_liquidity]
        liquidity_filtered_count = before_liquidity_filter - len(markets)
        before_clarity_filter = len(markets)
        markets = [market for market in markets if market.clarity_score >= selected.min_clarity_score]
        clarity_filtered_count = before_clarity_filter - len(markets)
        deduped: dict[str, MarketDescriptor] = {}
        deduped_market_ids: list[str] = []
        dedupe_groups: dict[str, list[str]] = {}
        for market in markets:
            key = self._dedupe_key(market)
            if key not in deduped or self._score(market) > self._score(deduped[key]):
                if key in deduped:
                    deduped_market_ids.append(deduped[key].market_id)
                deduped[key] = market
            else:
                deduped_market_ids.append(market.market_id)
            dedupe_groups.setdefault(key, [])
            if market.market_id not in dedupe_groups[key]:
                dedupe_groups[key].append(market.market_id)
        deduplicated_market_ids = list(dict.fromkeys(deduped_market_ids))
        eligible_market_count = len(markets)
        duplicate_group_count = sum(1 for market_ids in dedupe_groups.values() if len(market_ids) > 1)
        dedupe_group_sizes = [len(market_ids) for market_ids in dedupe_groups.values()]
        ranked = sorted(deduped.values(), key=self._score, reverse=True)[: selected.limit]
        return MarketUniverseResult(
            venue=selected.venue,
            config=selected,
            markets=ranked,
            filtered_out=filtered_out,
            metadata={
                "input_count": input_count,
                "eligible_market_count": eligible_market_count,
                "eligible_market_rate": round(eligible_market_count / max(1, input_count), 6),
                "active_filtered_count": len(filtered_out),
                "liquidity_filtered_count": liquidity_filtered_count,
                "clarity_filtered_count": clarity_filtered_count,
                "kept_count": len(ranked),
                "kept_rate": round(len(ranked) / max(1, input_count), 6),
                "filtered_out_count": len(filtered_out) + liquidity_filtered_count + clarity_filtered_count,
                "filtered_out_rate": round((len(filtered_out) + liquidity_filtered_count + clarity_filtered_count) / max(1, input_count), 6),
                "coverage_gap_count": max(0, eligible_market_count - len(ranked)),
                "coverage_gap_rate": round(max(0, eligible_market_count - len(ranked)) / max(1, eligible_market_count), 6),
                "duplicate_market_count": len(deduplicated_market_ids),
                "duplicate_market_rate": round(len(deduplicated_market_ids) / max(1, eligible_market_count), 6),
                "dedupe_rate": round(len(deduplicated_market_ids) / max(1, eligible_market_count), 3),
                "query": selected.query,
                "include_watchlist": selected.include_watchlist,
                "dedupe_group_count": len(dedupe_groups),
                "duplicate_group_count": duplicate_group_count,
                "max_dedupe_group_size": max(dedupe_group_sizes, default=0),
                "average_dedupe_group_size": round(sum(dedupe_group_sizes) / max(1, len(dedupe_group_sizes)), 6) if dedupe_group_sizes else 0.0,
                "coverage_after_dedupe_rate": round(len(ranked) / max(1, eligible_market_count), 6),
                "deduplicated_market_ids": deduplicated_market_ids,
                "dedupe_groups": dedupe_groups,
            },
        )

    def get(self, market_id: str) -> MarketDescriptor:
        return self.adapter.get_market(market_id)

    def events(self, market_id: str) -> list[MarketDescriptor]:
        return self.adapter.get_events(market_id)

    def positions(self, market_id: str) -> list[LedgerPosition]:
        return self.adapter.get_positions(market_id)

    def describe_data_surface(self) -> dict[str, object]:
        capabilities = self.adapter.describe_capabilities() if hasattr(self.adapter, "describe_capabilities") else None
        metadata_map = dict(getattr(capabilities, "metadata_map", {}) or {})
        venue = getattr(capabilities, "venue", VenueName.polymarket)
        capability = DEFAULT_VENUE_EXECUTION_REGISTRY.capability_for(venue)
        coverage_report = DEFAULT_VENUE_EXECUTION_REGISTRY.coverage_report()
        default_backend_name = str(metadata_map.get("backend_mode", getattr(self.adapter, "backend_mode", "unknown"))).strip().lower()
        supports_positions = bool(getattr(capabilities, "positions", False))
        feed_surface = None
        if hasattr(self.adapter, "describe_data_surface"):
            try:
                feed_surface = self.adapter.describe_data_surface()
            except Exception:
                feed_surface = None
        feed_surface_map = feed_surface.model_dump(mode="json") if hasattr(feed_surface, "model_dump") else dict(feed_surface or {})
        if not feed_surface_map:
            feed_surface_map = {
                "venue": venue.value,
                "venue_type": capability.venue_type.value if capability.venue_type else None,
                "backend_mode": metadata_map.get("backend_mode", getattr(self.adapter, "backend_mode", "unknown")),
                "ingestion_mode": "read_only",
                "supports_discovery": bool(getattr(capabilities, "discovery", capability.supports_discovery)),
                "supports_orderbook": bool(getattr(capabilities, "orderbook", capability.supports_orderbook)),
                "supports_trades": bool(getattr(capabilities, "trades", capability.supports_trades)),
                "supports_execution": bool(getattr(capabilities, "execution", capability.supports_execution)),
                "supports_websocket": False,
                "supports_rtds": False,
                "supports_paper_mode": capability.supports_paper_mode,
                "supports_market_feed": True,
                "supports_user_feed": bool(getattr(capabilities, "positions", False)),
                "supports_events": bool(getattr(capabilities, "discovery", False)),
                "supports_positions": bool(getattr(capabilities, "positions", False)),
                "live_streaming": False,
                "market_feed_transport": "http_json"
                if default_backend_name == "live"
                else ("fixture_cache" if default_backend_name == "fixture" else "surrogate_snapshot"),
                "user_feed_transport": "http_json"
                if default_backend_name == "live" and supports_positions
                else ("fixture_cache" if default_backend_name == "fixture" and supports_positions else ("local_cache" if supports_positions else "unavailable")),
                "events_source": "events"
                if default_backend_name == "live"
                else ("fixtures/events.json" if default_backend_name == "fixture" else "surrogate_market_catalog"),
                "positions_source": "positions"
                if default_backend_name == "live" and supports_positions
                else ("fixtures/positions.json" if default_backend_name == "fixture" and supports_positions else ("local_position_cache" if supports_positions else "unavailable")),
                "market_feed_source": "market-feed"
                if default_backend_name == "live"
                else ("fixtures/markets.json" if default_backend_name == "fixture" else "surrogate_snapshot"),
                "user_feed_source": "user-feed"
                if default_backend_name == "live" and supports_positions
                else ("fixtures/positions.json" if default_backend_name == "fixture" and supports_positions else ("local_position_cache" if supports_positions else "unavailable")),
                "configured_endpoints": {
                    "events_source": "events"
                    if default_backend_name == "live"
                    else ("fixtures/events.json" if default_backend_name == "fixture" else "surrogate_market_catalog"),
                    "positions_source": "positions"
                    if default_backend_name == "live" and supports_positions
                    else ("fixtures/positions.json" if default_backend_name == "fixture" and supports_positions else ("local_position_cache" if supports_positions else "unavailable")),
                    "market_feed_source": "market-feed"
                    if default_backend_name == "live"
                    else ("fixtures/markets.json" if default_backend_name == "fixture" else "surrogate_snapshot"),
                    "user_feed_source": "user-feed"
                    if default_backend_name == "live" and supports_positions
                    else ("fixtures/positions.json" if default_backend_name == "fixture" and supports_positions else ("local_position_cache" if supports_positions else "unavailable")),
                },
                "market_websocket_status": "unavailable",
                "user_feed_websocket_status": "unavailable",
                "market_feed_status": "endpoint_configured"
                if default_backend_name == "live"
                else (
                    "fixture_available"
                    if default_backend_name == "fixture"
                    else (
                        "surrogate_available"
                        if default_backend_name == "surrogate"
                        else "unavailable"
                    )
                ),
                "user_feed_status": "endpoint_configured"
                if default_backend_name == "live" and supports_positions
                else (
                    "fixture_available"
                    if default_backend_name == "fixture" and supports_positions
                    else ("local_cache" if supports_positions else "unavailable")
                ),
                "market_feed_connector": "http_json_market_snapshot"
                if default_backend_name == "live"
                else (
                    "fixture_market_snapshot"
                    if default_backend_name == "fixture"
                    else (
                        "surrogate_market_snapshot"
                        if default_backend_name == "surrogate"
                        else "snapshot_polling"
                    )
                ),
                "user_feed_connector": "http_json_position_snapshot"
                if default_backend_name == "live" and supports_positions
                else (
                    "fixture_positions_snapshot"
                    if default_backend_name == "fixture" and supports_positions
                    else ("local_position_cache" if supports_positions else "unavailable")
                ),
                "rtds_connector": "unavailable",
                "market_feed_replayable": True,
                "user_feed_replayable": supports_positions,
                "rtds_replayable": False,
                "market_feed_cache_backed": True,
                "user_feed_cache_backed": supports_positions,
                "rtds_cache_backed": False,
                "degraded": True,
                "degraded_reasons": [
                    "read_only_ingestion",
                    "no_websocket_live_integration",
                    "no_rtds_live_integration",
                ],
                "api_access": list(capability.api_access or capability.metadata.get("api_access", []) or []),
                "supported_order_types": list(capability.supported_order_types or capability.metadata.get("supported_order_types", []) or []),
                "rate_limit_notes": list(capability.rate_limit_notes),
                "automation_constraints": list(capability.automation_constraints),
            }
        degraded_reasons = list(feed_surface_map.get("degraded_reasons", []) or [])
        if not degraded_reasons:
            if str(feed_surface_map.get("ingestion_mode", "")).startswith("read_only"):
                degraded_reasons.append("read_only_ingestion")
            if not bool(feed_surface_map.get("supports_websocket", False)):
                degraded_reasons.append("no_websocket_live_integration")
            if not bool(feed_surface_map.get("supports_rtds", False)):
                degraded_reasons.append("no_rtds_live_integration")
            degraded_reasons = list(dict.fromkeys(degraded_reasons))
        degraded = bool(feed_surface_map.get("degraded", bool(degraded_reasons)))
        backend_name = str(feed_surface_map.get("backend_mode", metadata_map.get("backend_mode", getattr(self.adapter, "backend_mode", "unknown")))).strip().lower()
        feed_surface_map.setdefault("websocket_status", "unavailable")
        feed_surface_map.setdefault("rtds_status", "unavailable")
        feed_surface_map.setdefault("market_websocket_status", feed_surface_map.get("websocket_status", "unavailable"))
        feed_surface_map.setdefault("user_feed_websocket_status", "unavailable")
        feed_surface_map.setdefault(
            "market_feed_status",
            "endpoint_configured"
            if backend_name == "live"
            else ("fixture_available" if backend_name == "fixture" else ("surrogate_available" if backend_name == "surrogate" else "unavailable")),
        )
        feed_surface_map.setdefault(
            "user_feed_status",
            "endpoint_configured"
            if backend_name == "live" and bool(feed_surface_map.get("supports_positions", False))
            else (
                "fixture_available"
                if backend_name == "fixture" and bool(feed_surface_map.get("supports_positions", False))
                else ("local_cache" if bool(feed_surface_map.get("supports_positions", False)) else "unavailable")
            ),
        )
        feed_surface_map.setdefault(
            "market_feed_connector",
            "http_json_market_snapshot"
            if backend_name == "live"
            else ("fixture_market_snapshot" if backend_name == "fixture" else ("surrogate_market_snapshot" if backend_name == "surrogate" else "snapshot_polling")),
        )
        feed_surface_map.setdefault(
            "user_feed_connector",
            "http_json_position_snapshot"
            if backend_name == "live" and bool(feed_surface_map.get("supports_positions", False))
            else (
                "fixture_positions_snapshot"
                if backend_name == "fixture" and bool(feed_surface_map.get("supports_positions", False))
                else ("local_position_cache" if bool(feed_surface_map.get("supports_positions", False)) else "unavailable")
            ),
        )
        feed_surface_map.setdefault("rtds_connector", "unavailable")
        feed_surface_map.setdefault("market_feed_replayable", True)
        feed_surface_map.setdefault("user_feed_replayable", bool(feed_surface_map.get("supports_positions", False)))
        feed_surface_map.setdefault("rtds_replayable", False)
        feed_surface_map.setdefault("market_feed_cache_backed", backend_name != "live")
        feed_surface_map.setdefault("user_feed_cache_backed", bool(feed_surface_map.get("supports_positions", False)) and backend_name != "live")
        feed_surface_map.setdefault("rtds_cache_backed", False)
        feed_surface_map.setdefault(
            "market_feed_transport",
            "http_json" if backend_name == "live" else ("fixture_cache" if backend_name == "fixture" else "surrogate_snapshot"),
        )
        feed_surface_map.setdefault(
            "user_feed_transport",
            "http_json"
            if backend_name == "live" and bool(feed_surface_map.get("supports_positions", False))
            else ("fixture_cache" if backend_name == "fixture" and bool(feed_surface_map.get("supports_positions", False)) else ("local_cache" if bool(feed_surface_map.get("supports_positions", False)) else "unavailable")),
        )
        feed_surface_map.setdefault(
            "events_source",
            "events" if backend_name == "live" else ("fixtures/events.json" if backend_name == "fixture" else "surrogate_market_catalog"),
        )
        feed_surface_map.setdefault(
            "positions_source",
            "positions"
            if backend_name == "live" and bool(feed_surface_map.get("supports_positions", False))
            else ("fixtures/positions.json" if backend_name == "fixture" and bool(feed_surface_map.get("supports_positions", False)) else ("local_position_cache" if bool(feed_surface_map.get("supports_positions", False)) else "unavailable")),
        )
        feed_surface_map.setdefault(
            "market_feed_source",
            "market-feed" if backend_name == "live" else ("fixtures/markets.json" if backend_name == "fixture" else "surrogate_snapshot"),
        )
        feed_surface_map.setdefault(
            "user_feed_source",
            "user-feed"
            if backend_name == "live" and bool(feed_surface_map.get("supports_positions", False))
            else ("fixtures/positions.json" if backend_name == "fixture" and bool(feed_surface_map.get("supports_positions", False)) else ("local_position_cache" if bool(feed_surface_map.get("supports_positions", False)) else "unavailable")),
        )
        feed_surface_map.setdefault(
            "configured_endpoints",
            {
                "events_source": feed_surface_map.get("events_source"),
                "positions_source": feed_surface_map.get("positions_source"),
                "market_feed_source": feed_surface_map.get("market_feed_source"),
                "user_feed_source": feed_surface_map.get("user_feed_source"),
            },
        )
        route_refs = _surface_route_refs(feed_surface_map)
        existing_route_refs = feed_surface_map.get("route_refs")
        if isinstance(existing_route_refs, dict):
            merged_route_refs = dict(route_refs)
            merged_route_refs.update({str(key): str(value) for key, value in existing_route_refs.items() if value is not None})
            feed_surface_map["route_refs"] = merged_route_refs
        else:
            feed_surface_map["route_refs"] = route_refs
        probes = _surface_availability_probes(feed_surface_map)
        existing_probes = feed_surface_map.get("availability_probes")
        if isinstance(existing_probes, dict):
            merged_probes = dict(probes)
            merged_probes.update(existing_probes)
            feed_surface_map["availability_probes"] = merged_probes
        else:
            feed_surface_map["availability_probes"] = probes
        cache_fallbacks = _surface_cache_fallbacks(feed_surface_map)
        existing_fallbacks = feed_surface_map.get("cache_fallbacks")
        if isinstance(existing_fallbacks, dict):
            merged_fallbacks = dict(cache_fallbacks)
            merged_fallbacks.update(existing_fallbacks)
            feed_surface_map["cache_fallbacks"] = merged_fallbacks
        else:
            feed_surface_map["cache_fallbacks"] = cache_fallbacks
        connector_contracts = _surface_connector_contracts(feed_surface_map)
        existing_connector_contracts = feed_surface_map.get("connector_contracts")
        if isinstance(existing_connector_contracts, dict):
            merged_connector_contracts = dict(connector_contracts)
            merged_connector_contracts.update(existing_connector_contracts)
            feed_surface_map["connector_contracts"] = merged_connector_contracts
        else:
            feed_surface_map["connector_contracts"] = connector_contracts
        subscription_preview = _surface_subscription_preview(feed_surface_map)
        existing_subscription_preview = feed_surface_map.get("subscription_preview")
        if isinstance(existing_subscription_preview, dict):
            merged_subscription_preview = dict(subscription_preview)
            merged_subscription_preview.update(existing_subscription_preview)
            feed_surface_map["subscription_preview"] = merged_subscription_preview
        else:
            feed_surface_map["subscription_preview"] = subscription_preview
        probe_bundle = _surface_probe_bundle(feed_surface_map)
        existing_probe_bundle = feed_surface_map.get("probe_bundle")
        if isinstance(existing_probe_bundle, dict):
            merged_probe_bundle = dict(probe_bundle)
            merged_probe_bundle.update(existing_probe_bundle)
            feed_surface_map["probe_bundle"] = merged_probe_bundle
        else:
            feed_surface_map["probe_bundle"] = probe_bundle
        capability_summary = _surface_capability_summary(feed_surface_map)
        existing_capability_summary = feed_surface_map.get("capability_summary")
        if isinstance(existing_capability_summary, dict):
            merged_capability_summary = dict(capability_summary)
            merged_capability_summary.update(existing_capability_summary)
            feed_surface_map["capability_summary"] = merged_capability_summary
        else:
            feed_surface_map["capability_summary"] = capability_summary
        feed_surface_map.setdefault("feed_surface_status", feed_surface_map.get("feed_surface_status") or feed_surface_map.get("ingestion_mode", "read_only"))
        feed_surface_map.setdefault("feed_surface_summary", str(feed_surface_map.get("feed_surface_summary") or feed_surface_map.get("summary", "")))
        feed_surface_map.setdefault("feed_surface_degraded", degraded)
        feed_surface_map.setdefault("feed_surface_degraded_reasons", list(degraded_reasons))
        feed_surface_map.setdefault("metadata_gap_count", int(feed_surface_map.get("metadata_gap_count", 0) or 0))
        feed_surface_map.setdefault("metadata_gap_rate", float(feed_surface_map.get("metadata_gap_rate", 0.0) or 0.0))
        feed_surface_map.setdefault("metadata_completeness", float(feed_surface_map.get("metadata_completeness", 1.0) or 1.0))
        return {
            "venue": venue.value,
            "venue_type": (capability.venue_type.value if capability.venue_type else metadata_map.get("venue_type")),
            "supports_discovery": bool(getattr(capabilities, "discovery", capability.supports_discovery)),
            "supports_orderbook": bool(getattr(capabilities, "orderbook", capability.supports_orderbook)),
            "supports_trades": bool(getattr(capabilities, "trades", capability.supports_trades)),
            "supports_execution": bool(getattr(capabilities, "execution", capability.supports_execution)),
            "supports_websocket": bool(feed_surface_map.get("supports_websocket", capability.supports_websocket)),
            "supports_paper_mode": bool(capability.supports_paper_mode),
            "rate_limit_notes": list(capability.rate_limit_notes),
            "automation_constraints": list(capability.automation_constraints),
            "api_access": list(capability.api_access or capability.metadata.get("api_access", []) or []),
            "supported_order_types": list(capability.supported_order_types or capability.metadata.get("supported_order_types", []) or []),
            "supports_events": hasattr(self.adapter, "get_events"),
            "supports_positions": hasattr(self.adapter, "get_positions"),
            "supports_market_feed": True,
            "supports_user_feed": hasattr(self.adapter, "get_positions"),
            "supports_rtds": bool(feed_surface_map.get("supports_rtds", False)),
            "websocket_status": str(feed_surface_map.get("websocket_status", "unavailable")),
            "rtds_status": str(feed_surface_map.get("rtds_status", "unavailable")),
            "market_websocket_status": str(feed_surface_map.get("market_websocket_status", feed_surface_map.get("websocket_status", "unavailable"))),
            "user_feed_websocket_status": str(feed_surface_map.get("user_feed_websocket_status", "unavailable")),
            "market_feed_status": str(feed_surface_map.get("market_feed_status", "unavailable")),
            "user_feed_status": str(feed_surface_map.get("user_feed_status", "unavailable")),
            "market_feed_connector": str(feed_surface_map.get("market_feed_connector", "snapshot_polling")),
            "user_feed_connector": str(feed_surface_map.get("user_feed_connector", "unavailable")),
            "rtds_connector": str(feed_surface_map.get("rtds_connector", "unavailable")),
            "market_feed_replayable": bool(feed_surface_map.get("market_feed_replayable", True)),
            "user_feed_replayable": bool(feed_surface_map.get("user_feed_replayable", False)),
            "rtds_replayable": bool(feed_surface_map.get("rtds_replayable", False)),
            "market_feed_cache_backed": bool(feed_surface_map.get("market_feed_cache_backed", False)),
            "user_feed_cache_backed": bool(feed_surface_map.get("user_feed_cache_backed", False)),
            "rtds_cache_backed": bool(feed_surface_map.get("rtds_cache_backed", False)),
            "route_refs": dict(feed_surface_map.get("route_refs") or {}),
            "availability_probes": dict(feed_surface_map.get("availability_probes") or {}),
            "cache_fallbacks": dict(feed_surface_map.get("cache_fallbacks") or {}),
            "subscription_preview": dict(feed_surface_map.get("subscription_preview") or {}),
            "probe_bundle": dict(feed_surface_map.get("probe_bundle") or {}),
            "capability_summary": dict(feed_surface_map.get("capability_summary") or {}),
            "connector_contracts": dict(feed_surface_map.get("connector_contracts") or {}),
            "gap_summary": _surface_gap_summary(feed_surface_map),
            "feed_surface_status": str(feed_surface_map.get("feed_surface_status") or feed_surface_map.get("ingestion_mode", "read_only")),
            "feed_surface_summary": str(feed_surface_map.get("feed_surface_summary") or feed_surface_map.get("summary", "")),
            "feed_surface_degraded": degraded,
            "feed_surface_degraded_reasons": degraded_reasons,
            "live_streaming": bool(feed_surface_map.get("live_streaming", False)),
            "execution_equivalent": DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(venue).execution_equivalent,
            "execution_like": DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(venue).execution_like,
            "read_only": DEFAULT_VENUE_EXECUTION_REGISTRY.is_read_only(venue),
            "paper_capable": DEFAULT_VENUE_EXECUTION_REGISTRY.is_paper_capable(venue),
            "execution_capable": DEFAULT_VENUE_EXECUTION_REGISTRY.is_execution_capable(venue),
            "feed_surface_runbook": dict(feed_surface_map.get("runbook") or {}),
            "metadata_gap_count": int(feed_surface_map.get("metadata_gap_count", 0) or 0),
            "metadata_gap_rate": float(feed_surface_map.get("metadata_gap_rate", 0.0) or 0.0),
            "metadata_completeness": float(feed_surface_map.get("metadata_completeness", 1.0) or 1.0),
            "coverage_report": coverage_report.model_dump(mode="json"),
            "availability_by_venue": {
                key: value.model_dump(mode="json")
                for key, value in coverage_report.availability_by_venue.items()
            },
            "registry_coverage": {
                "venue_count": coverage_report.venue_count,
                "execution_capable_count": coverage_report.execution_capable_count,
                "paper_capable_count": coverage_report.paper_capable_count,
                "read_only_count": coverage_report.read_only_count,
                "degraded_venue_count": coverage_report.degraded_venue_count,
                "degraded_venue_rate": coverage_report.degraded_venue_rate,
                "execution_equivalent_count": coverage_report.execution_equivalent_count,
                "execution_like_count": coverage_report.execution_like_count,
                "reference_only_count": coverage_report.reference_only_count,
                "watchlist_only_count": coverage_report.watchlist_only_count,
                "metadata_gap_count": coverage_report.metadata_gap_count,
                "metadata_gap_rate": coverage_report.metadata_gap_rate,
                "execution_surface_rate": coverage_report.execution_surface_rate,
            },
            "backend_mode": metadata_map.get("backend_mode", getattr(self.adapter, "backend_mode", "unknown")),
            "market_feed_transport": str(feed_surface_map.get("market_feed_transport", metadata_map.get("market_feed_transport", "polled_snapshot"))),
            "user_feed_transport": str(feed_surface_map.get("user_feed_transport", metadata_map.get("user_feed_transport", "local_position_cache"))),
            "events_source": str(feed_surface_map.get("events_source", "")),
            "positions_source": str(feed_surface_map.get("positions_source", "")),
            "market_feed_source": str(feed_surface_map.get("market_feed_source", "")),
            "user_feed_source": str(feed_surface_map.get("user_feed_source", "")),
            "configured_endpoints": dict(feed_surface_map.get("configured_endpoints") or {}),
            "feed_surface": feed_surface_map,
            "notes": [
                "read_only_surface",
                "no_websocket_live_integration",
                "no_rtds_live_integration",
            ],
        }

    def describe_health_surface(self) -> dict[str, object]:
        surface = self.describe_data_surface()
        return {
            "venue": surface["venue"],
            "backend_mode": surface["backend_mode"],
            "supports_websocket": surface["supports_websocket"],
            "supports_rtds": surface["supports_rtds"],
            "websocket_status": surface["websocket_status"],
            "rtds_status": surface["rtds_status"],
            "market_websocket_status": surface["market_websocket_status"],
            "user_feed_websocket_status": surface["user_feed_websocket_status"],
            "market_feed_status": surface["market_feed_status"],
            "user_feed_status": surface["user_feed_status"],
            "market_feed_connector": surface["market_feed_connector"],
            "user_feed_connector": surface["user_feed_connector"],
            "rtds_connector": surface["rtds_connector"],
            "market_feed_replayable": surface["market_feed_replayable"],
            "user_feed_replayable": surface["user_feed_replayable"],
            "rtds_replayable": surface["rtds_replayable"],
            "market_feed_cache_backed": surface["market_feed_cache_backed"],
            "user_feed_cache_backed": surface["user_feed_cache_backed"],
            "rtds_cache_backed": surface["rtds_cache_backed"],
            "route_refs": dict(surface["route_refs"]),
            "availability_probes": dict(surface["availability_probes"]),
            "cache_fallbacks": dict(surface["cache_fallbacks"]),
            "subscription_preview": dict(surface["subscription_preview"]),
            "probe_bundle": dict(surface["probe_bundle"]),
            "capability_summary": dict(surface["capability_summary"]),
            "connector_contracts": dict(surface["connector_contracts"]),
            "gap_summary": _surface_gap_summary(surface),
            "feed_surface_status": surface["feed_surface_status"],
            "feed_surface_summary": surface["feed_surface_summary"],
            "feed_surface_degraded": surface["feed_surface_degraded"],
            "feed_surface_degraded_reasons": list(surface["feed_surface_degraded_reasons"]),
            "metadata_gap_count": surface["metadata_gap_count"],
            "metadata_gap_rate": surface["metadata_gap_rate"],
            "metadata_completeness": surface["metadata_completeness"],
            "execution_equivalent": surface["execution_equivalent"],
            "execution_like": surface["execution_like"],
            "read_only": surface["read_only"],
            "paper_capable": surface["paper_capable"],
            "execution_capable": surface["execution_capable"],
            "rate_limit_notes": list(surface["rate_limit_notes"]),
            "automation_constraints": list(surface["automation_constraints"]),
            "feed_surface_runbook": dict(surface["feed_surface_runbook"]),
            "registry_coverage": dict(surface["registry_coverage"]),
        }

    @staticmethod
    def _score(market: MarketDescriptor) -> float:
        score = market.clarity_score
        if market.liquidity:
            score += min(0.3, market.liquidity / 100000.0)
        if market.status == MarketStatus.open:
            score += 0.1
        return score

    @staticmethod
    def _dedupe_key(market: MarketDescriptor) -> str:
        if market.canonical_event_id:
            return f"canonical:{market.canonical_event_id}"
        question_key = MarketGraphBuilder._question_key(market.question or market.title)
        resolution_source = (market.resolution_source or market.source_url or "").strip().lower()
        end_date = market.end_date.isoformat() if market.end_date is not None else ""
        category = (market.category or "").strip().lower()
        venue_type = market.venue_type.value
        return "|".join(
            [
                "question",
                question_key,
                resolution_source,
                end_date,
                category,
                venue_type,
            ]
        )
