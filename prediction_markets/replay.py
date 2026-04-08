from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .advisor import MarketAdvisor
from .adapters import MarketDataUnavailableError
from .evidence_registry import EvidenceRegistry
from pydantic import BaseModel, Field

from .models import EvidencePacket, ExecutionProjection, ExecutionReadiness, ReplayReport, RunManifest
from .paths import PredictionMarketPaths, default_prediction_market_paths
from .registry import RunRegistryStore
from .storage import file_signature, load_json, save_json, utc_isoformat


def execution_projection_signature(projection: ExecutionProjection | None) -> dict[str, Any] | None:
    if projection is None:
        return None
    signature = projection.model_dump(mode="json", exclude={"content_hash"})
    return _strip_execution_projection_bookkeeping(signature)


_EXECUTION_PROJECTION_BOOKKEEPING_KEYS = {
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


def _strip_execution_projection_bookkeeping(payload: Any) -> Any:
    if isinstance(payload, dict):
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            if key in _EXECUTION_PROJECTION_BOOKKEEPING_KEYS:
                continue
            cleaned[key] = _strip_execution_projection_bookkeeping(value)
        return cleaned
    if isinstance(payload, list):
        return [_strip_execution_projection_bookkeeping(item) for item in payload]
    return payload


def replay_difference_details(
    *,
    original_forecast: dict[str, Any],
    replay_forecast: dict[str, Any],
    original_recommendation: dict[str, Any],
    replay_recommendation: dict[str, Any],
    original_decision: dict[str, Any],
    replay_decision: dict[str, Any],
    original_execution_readiness: ExecutionReadiness | None,
    replay_execution_readiness: ExecutionReadiness | None,
    original_execution_projection: ExecutionProjection | None,
    replay_execution_projection: ExecutionProjection | None,
) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []

    def add_detail(field: str, original: Any, replay: Any, *, reason: str, kind: str = "surface") -> None:
        if original == replay:
            return
        details.append(
            {
                "field": field,
                "kind": kind,
                "reason": reason,
                "original": original,
                "replay": replay,
            }
        )

    add_detail(
        "recommendation_action",
        original_forecast.get("recommendation_action"),
        replay_forecast.get("recommendation_action"),
        reason="forecast recommendation action changed",
    )
    add_detail(
        "recommendation.action",
        original_recommendation.get("action"),
        replay_recommendation.get("action"),
        reason="recommendation action changed",
    )
    add_detail(
        "decision.action",
        original_decision.get("action"),
        replay_decision.get("action"),
        reason="decision action changed",
    )

    original_readiness_signature = MarketReplayRunner._readiness_signature(original_execution_readiness)
    replay_readiness_signature = MarketReplayRunner._readiness_signature(replay_execution_readiness)
    add_detail(
        "execution_readiness",
        original_readiness_signature,
        replay_readiness_signature,
        reason="execution readiness signature changed",
        kind="signature",
    )

    add_detail(
        "edge_after_fees_bps",
        original_forecast.get("edge_after_fees_bps"),
        replay_forecast.get("edge_after_fees_bps"),
        reason="edge after fees changed",
    )
    add_detail(
        "next_review_at",
        original_forecast.get("next_review_at") or (original_forecast.get("metadata") or {}).get("next_review_at"),
        replay_forecast.get("next_review_at") or (replay_forecast.get("metadata") or {}).get("next_review_at"),
        reason="next review timestamp changed",
    )
    add_detail(
        "resolution_policy_missing",
        bool((original_forecast.get("metadata") or {}).get("resolution_policy_missing", False)),
        bool((replay_forecast.get("metadata") or {}).get("resolution_policy_missing", False)),
        reason="resolution policy missing flag changed",
    )

    original_projection_signature = execution_projection_signature(original_execution_projection)
    replay_projection_signature = execution_projection_signature(replay_execution_projection)
    add_detail(
        "execution_projection",
        original_projection_signature,
        replay_projection_signature,
        reason="execution projection signature changed",
        kind="signature",
    )
    return details


def _coerce_mapping(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return dict(payload)
    model_dump = getattr(payload, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json")
        if isinstance(dumped, dict):
            return dict(dumped)
    return {}


def _report_surface_context(report_data: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}

    order_trace_audit = _coerce_mapping(report_data.get("order_trace_audit"))
    if order_trace_audit:
        context["order_trace_audit"] = order_trace_audit

    research_bridge = _coerce_mapping(report_data.get("research_bridge"))
    if research_bridge:
        context["research_bridge"] = research_bridge

    market_execution = _coerce_mapping(report_data.get("market_execution"))
    execution_surface = {}
    if market_execution:
        capability = _coerce_mapping(market_execution.get("capability"))
        capability_metadata = _coerce_mapping(capability.get("metadata"))
        execution_plan = _coerce_mapping(market_execution.get("execution_plan"))
        execution_plan_metadata = _coerce_mapping(execution_plan.get("metadata"))

        planning_bucket = (
            capability_metadata.get("planning_bucket")
            or execution_plan_metadata.get("planning_bucket")
            or capability_metadata.get("tradeability_class")
            or execution_plan_metadata.get("tradeability_class")
        )
        execution_surface = {
            "planning_bucket": planning_bucket,
            "execution_equivalent": bool(capability_metadata.get("execution_equivalent") or capability.get("execution_equivalent")),
            "execution_like": bool(capability_metadata.get("execution_like") or capability.get("execution_like")),
            "tradeability_class": capability_metadata.get("tradeability_class") or capability.get("tradeability_class"),
            "venue_taxonomy": capability_metadata.get("venue_taxonomy") or capability.get("venue_taxonomy"),
            "supports_execution": capability.get("supports_execution"),
            "supports_paper_mode": capability.get("supports_paper_mode"),
        }
        execution_surface = {key: value for key, value in execution_surface.items() if value is not None}

    if execution_surface:
        context["execution_surface"] = execution_surface

    feed_surface = _coerce_mapping(report_data.get("feed_surface"))
    if not feed_surface:
        feed_surface = _coerce_mapping(report_data.get("data_surface"))
    if not feed_surface:
        feed_surface = _coerce_mapping(_coerce_mapping(report_data.get("metadata")).get("data_surface"))
    if feed_surface:
        feed_context = {
            "supports_websocket": feed_surface.get("supports_websocket"),
            "supports_rtds": feed_surface.get("supports_rtds"),
            "websocket_status": feed_surface.get("websocket_status"),
            "rtds_status": feed_surface.get("rtds_status"),
            "market_feed_status": feed_surface.get("market_feed_status"),
            "user_feed_status": feed_surface.get("user_feed_status"),
            "feed_surface_status": feed_surface.get("feed_surface_status") or feed_surface.get("ingestion_mode"),
            "feed_surface_summary": feed_surface.get("feed_surface_summary") or feed_surface.get("summary"),
            "feed_surface_degraded": feed_surface.get("feed_surface_degraded", feed_surface.get("degraded")),
            "feed_surface_degraded_reasons": feed_surface.get("feed_surface_degraded_reasons") or feed_surface.get("degraded_reasons"),
            "market_feed_transport": feed_surface.get("market_feed_transport"),
            "user_feed_transport": feed_surface.get("user_feed_transport"),
            "live_streaming": feed_surface.get("live_streaming"),
        }
        feed_context = {key: value for key, value in feed_context.items() if value is not None}
        if feed_context:
            context["feed_surface"] = feed_context

    health_surface = _coerce_mapping(report_data.get("health_surface"))
    if not health_surface:
        health_surface = _coerce_mapping(_coerce_mapping(report_data.get("metadata")).get("health_surface"))
    if health_surface:
        health_context = {
            "healthy": health_surface.get("healthy"),
            "stream_status": health_surface.get("stream_status"),
            "freshness_status": health_surface.get("freshness_status"),
            "message": health_surface.get("message"),
            "supports_websocket": health_surface.get("supports_websocket"),
            "supports_rtds": health_surface.get("supports_rtds"),
            "websocket_status": health_surface.get("websocket_status"),
            "rtds_status": health_surface.get("rtds_status"),
            "feed_surface_status": health_surface.get("feed_surface_status"),
            "feed_surface_summary": health_surface.get("feed_surface_summary"),
            "feed_surface_degraded": health_surface.get("feed_surface_degraded"),
            "feed_surface_degraded_reasons": health_surface.get("feed_surface_degraded_reasons"),
        }
        health_context = {key: value for key, value in health_context.items() if value is not None}
        if health_context:
            context["health_surface"] = health_context

    social_bridge = _coerce_mapping(report_data.get("social_bridge"))
    if social_bridge:
        context["social_bridge"] = social_bridge

    taxonomy_context = _report_taxonomy_context(report_data)
    if taxonomy_context:
        context.update(taxonomy_context)

    return context


def _report_taxonomy_context(report_data: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    taxonomy_values: list[str] = []
    reason_codes: list[str] = []

    def add_taxonomy(value: Any) -> None:
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                taxonomy_values.append(cleaned)

    def add_reason_codes(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    cleaned = item.strip()
                    if cleaned:
                        reason_codes.append(cleaned)

    def inspect_mapping(mapping: dict[str, Any]) -> None:
        add_taxonomy(mapping.get("taxonomy"))
        add_reason_codes(mapping.get("execution_filter_reason_codes"))
        add_reason_codes(mapping.get("execution_filter_reason_codes_present"))
        for counts_key in ("execution_filter_reason_code_counts", "comparison_taxonomy_counts", "candidate_taxonomy_counts", "plan_taxonomy_counts"):
            counts = _coerce_mapping(mapping.get(counts_key))
            if not counts:
                continue
            if "taxonomy" in counts_key:
                for value in counts.keys():
                    add_taxonomy(value)
            else:
                for value in counts.keys():
                    if isinstance(value, str):
                        cleaned = value.strip()
                        if cleaned:
                            reason_codes.append(cleaned)

    inspect_mapping(report_data)
    inspect_mapping(_coerce_mapping(report_data.get("surface")))
    inspect_mapping(_coerce_mapping(report_data.get("metadata")))
    for nested_key in ("execution_candidates", "execution_plans", "comparisons", "plans", "plan_results"):
        nested_values = report_data.get(nested_key)
        if not isinstance(nested_values, list):
            continue
        for item in nested_values:
            item_mapping = _coerce_mapping(item)
            inspect_mapping(item_mapping)
            inspect_mapping(_coerce_mapping(item_mapping.get("surface")))
            inspect_mapping(_coerce_mapping(item_mapping.get("metadata")))

    unique_taxonomies = list(dict.fromkeys(taxonomy_values))
    if len(unique_taxonomies) == 1:
        context["taxonomy"] = unique_taxonomies[0]
    elif unique_taxonomies:
        context["taxonomy_counts"] = {taxonomy: taxonomy_values.count(taxonomy) for taxonomy in unique_taxonomies}

    unique_reason_codes = list(dict.fromkeys(reason_codes))
    if unique_reason_codes:
        context["execution_filter_reason_codes"] = unique_reason_codes

    return context


@dataclass
class MarketReplayRunner:
    advisor: MarketAdvisor
    paths: PredictionMarketPaths | None = None

    def __post_init__(self) -> None:
        self.paths = self.paths or getattr(self.advisor, "paths", None) or default_prediction_market_paths()
        self.paths.ensure_layout()
        self.registry = RunRegistryStore(self.paths)
        self.evidence_registry = EvidenceRegistry(self.paths)

    def replay(self, run_id: str) -> ReplayReport:
        manifest_path = self._manifest_path(run_id)
        manifest_dir = manifest_path.parent
        manifest = RunManifest.model_validate(load_json(manifest_path))
        original_forecast_path = self._artifact_path(manifest, "forecast", self.paths.forecast_path(run_id), base_dir=manifest_dir)
        original_recommendation_path = self._artifact_path(manifest, "recommendation", self.paths.recommendation_path(run_id), base_dir=manifest_dir)
        original_decision_path = self._artifact_path(manifest, "decision", self.paths.decision_path(run_id), base_dir=manifest_dir)
        original_execution_readiness_path = self._artifact_path(
            manifest,
            "execution_readiness",
            self.paths.run_dir(run_id) / "execution_readiness.json",
            base_dir=manifest_dir,
        )
        original_execution_projection_path = self._artifact_path(
            manifest,
            "execution_projection",
            self.paths.run_dir(run_id) / "execution_projection.json",
            base_dir=manifest_dir,
        )
        original_report_path = self._artifact_path(manifest, "report", self.paths.report_path(run_id), base_dir=manifest_dir)
        original_snapshot_path = self._artifact_path(manifest, "snapshot", self.paths.snapshot_path(run_id), base_dir=manifest_dir)
        original_snapshot = load_json(original_snapshot_path) if original_snapshot_path.exists() else {}
        original_forecast = load_json(original_forecast_path)
        original_recommendation = load_json(original_recommendation_path)
        original_decision = load_json(original_decision_path)
        original_report_data = load_json(original_report_path) if original_report_path.exists() else {}
        original_report_metadata = self._artifact_metadata(original_report_path, original_report_data) if original_report_path.exists() else {}
        original_report_context = _report_surface_context(original_report_data) if isinstance(original_report_data, dict) else {}
        original_execution_readiness_data = original_report_data.get("execution_readiness") if isinstance(original_report_data, dict) else None
        original_execution_readiness = (
            ExecutionReadiness.model_validate(original_execution_readiness_data)
            if isinstance(original_execution_readiness_data, dict)
            else None
        )
        original_execution_projection = (
            ExecutionProjection.model_validate(load_json(original_execution_projection_path))
            if original_execution_projection_path.exists()
            else None
        )
        replay_evidence = self._load_evidence(manifest.evidence_refs)

        replay_run = None
        try:
            replay_run = self.advisor.advise(
                manifest.market_id,
                extra_evidence=replay_evidence,
                persist=False,
                record_evidence=False,
                run_id=f"{run_id}_replay",
                mode=f"{manifest.mode}_replay",
            )
        except MarketDataUnavailableError:
            replay_run = None

        if replay_run is not None:
            replay_forecast = replay_run.forecast.model_dump(mode="json")
            replay_recommendation = replay_run.recommendation.model_dump(mode="json")
            replay_decision = replay_run.decision.model_dump(mode="json")
            replay_execution_readiness = replay_run.execution_readiness
            replay_execution_projection = getattr(replay_run, "execution_projection", None)
            replay_created_at = replay_run.forecast.created_at
            original_next_review_at = original_forecast.get("next_review_at") or (original_forecast.get("metadata") or {}).get("next_review_at")
            if original_next_review_at is not None:
                replay_forecast["next_review_at"] = original_next_review_at
                replay_forecast_metadata = replay_forecast.setdefault("metadata", {})
                if isinstance(replay_forecast_metadata, dict):
                    replay_forecast_metadata["next_review_at"] = original_next_review_at
            if replay_execution_projection is None and original_execution_projection is not None:
                replay_execution_projection = original_execution_projection.model_copy(deep=True)
        else:
            replay_forecast = dict(original_forecast)
            replay_recommendation = dict(original_recommendation)
            replay_decision = dict(original_decision)
            replay_execution_readiness = original_execution_readiness
            replay_execution_projection = original_execution_projection
            replay_created_at = original_execution_readiness.created_at if original_execution_readiness else datetime.fromtimestamp(0)

        differences: list[str] = []
        same_forecast = original_forecast.get("recommendation_action") == replay_forecast.get("recommendation_action")
        same_recommendation = original_recommendation.get("action") == replay_recommendation.get("action")
        same_decision = original_decision.get("action") == replay_decision.get("action")
        same_execution_readiness = self._same_readiness(original_execution_readiness, replay_execution_readiness)
        if not same_forecast:
            differences.append("recommendation_action")
        if not same_recommendation:
            differences.append("recommendation.action")
        if not same_decision:
            differences.append("decision.action")
        if not same_execution_readiness:
            differences.append("execution_readiness")
        if original_forecast.get("edge_after_fees_bps") != replay_forecast.get("edge_after_fees_bps"):
            differences.append("edge_after_fees_bps")
        if execution_projection_signature(original_execution_projection) != execution_projection_signature(replay_execution_projection):
            differences.append("execution_projection")

        difference_details = replay_difference_details(
            original_forecast=original_forecast,
            replay_forecast=replay_forecast,
            original_recommendation=original_recommendation,
            replay_recommendation=replay_recommendation,
            original_decision=original_decision,
            replay_decision=replay_decision,
            original_execution_readiness=original_execution_readiness,
            replay_execution_readiness=replay_execution_readiness,
            original_execution_projection=original_execution_projection,
            replay_execution_projection=replay_execution_projection,
        )

        metadata: dict[str, Any] = {
            "manifest_path": str(manifest_path),
            "replay_report_path": str(self.paths.replay_report_path(run_id)),
            "difference_summary": {
                "count": len(differences),
                "fields": list(differences),
                "explained_count": len(difference_details),
                "source": "replay_run" if replay_run is not None else "artifact_fallback",
            },
            "difference_details": difference_details,
            "original_artifacts": {
                "manifest": self._artifact_metadata(manifest_path, manifest.model_dump(mode="json")),
                "snapshot": self._artifact_metadata(original_snapshot_path, original_snapshot),
                "forecast": self._artifact_metadata(original_forecast_path, original_forecast),
                "recommendation": self._artifact_metadata(original_recommendation_path, original_recommendation),
                "decision": self._artifact_metadata(original_decision_path, original_decision),
                "report": original_report_metadata,
                "execution_readiness": self._artifact_metadata(
                    original_execution_readiness_path,
                    original_execution_readiness.model_dump(mode="json") if original_execution_readiness else {},
                ),
                "execution_projection": self._artifact_metadata(
                    original_execution_projection_path,
                    original_execution_projection.model_dump(mode="json") if original_execution_projection else {},
                ),
            },
            "replay_artifacts": {
                "forecast": self._payload_metadata(replay_forecast, replay_created_at, source="replay_run" if replay_run is not None else "artifact_fallback"),
                "recommendation": self._payload_metadata(replay_recommendation, replay_created_at, source="replay_run" if replay_run is not None else "artifact_fallback"),
                "decision": self._payload_metadata(replay_decision, replay_created_at, source="replay_run" if replay_run is not None else "artifact_fallback"),
                "report": self._payload_metadata(original_report_data if isinstance(original_report_data, dict) else {}, replay_created_at, source="artifact_fallback" if replay_run is None else "replay_run"),
                "execution_readiness": self._payload_metadata(
                    replay_execution_readiness.model_dump(mode="json") if replay_execution_readiness else {},
                    replay_execution_readiness.created_at if replay_execution_readiness else replay_created_at,
                    source="replay_run" if replay_run is not None else "artifact_fallback",
                ),
                "execution_projection": self._payload_metadata(
                    replay_execution_projection.model_dump(mode="json") if replay_execution_projection else {},
                    replay_created_at,
                    source="replay_run" if replay_run is not None else "artifact_fallback",
                ),
            },
            "original_report_context": original_report_context,
        }

        replay_report = ReplayReport(
            run_id=run_id,
            same_forecast=same_forecast,
            same_recommendation=same_recommendation,
            same_decision=same_decision,
            same_execution_readiness=same_execution_readiness,
            differences=differences,
            original={
                "forecast": original_forecast,
                "recommendation": original_recommendation,
                "decision": original_decision,
                "execution_readiness": original_execution_readiness.model_dump(mode="json") if original_execution_readiness else None,
                "execution_projection": original_execution_projection.model_dump(mode="json") if original_execution_projection else None,
            },
            replay={
                "forecast": replay_forecast,
                "recommendation": replay_recommendation,
                "decision": replay_decision,
                "execution_readiness": replay_execution_readiness.model_dump(mode="json") if replay_execution_readiness else None,
                "execution_projection": replay_execution_projection.model_dump(mode="json") if replay_execution_projection else None,
            },
            original_execution_readiness=original_execution_readiness,
            replay_execution_readiness=replay_execution_readiness,
            original_execution_projection=original_execution_projection,
            replay_execution_projection=replay_execution_projection,
            metadata=metadata,
        )
        save_json(self.paths.replay_report_path(run_id), replay_report)
        return replay_report

    def _load_evidence(self, evidence_refs: list[str]) -> list[EvidencePacket]:
        evidence: list[EvidencePacket] = []
        for evidence_id in evidence_refs:
            packet = self.evidence_registry.get(evidence_id)
            if packet is not None:
                evidence.append(packet)
        return evidence

    def _manifest_path(self, run_id: str) -> Path:
        candidate = self.paths.run_manifest_path(run_id)
        if candidate.exists():
            return candidate
        try:
            manifest = self.registry.get_manifest(run_id)
        except Exception:
            return candidate
        manifest_path = self.paths.run_manifest_path(run_id)
        if manifest_path.exists():
            return manifest_path
        manifest_path = self.paths.root / "runs" / run_id / "manifest.json"
        if manifest_path.exists():
            return manifest_path
        return candidate

    @staticmethod
    def _artifact_path(manifest: RunManifest, artifact_name: str, fallback: Path, *, base_dir: Path | None = None) -> Path:
        artifact_path = manifest.artifact_paths.get(artifact_name)
        if artifact_path:
            resolved = Path(artifact_path)
            if resolved.is_absolute() or base_dir is None:
                return resolved
            return base_dir / resolved
        return fallback

    @staticmethod
    def _artifact_metadata(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = file_signature(path)
        payload_metadata = payload.get("metadata")
        if isinstance(payload_metadata, dict) and payload_metadata:
            metadata["source"] = payload_metadata.get("source")
        content_hash = payload.get("content_hash")
        if isinstance(content_hash, str) and content_hash:
            metadata["content_hash"] = content_hash
        timestamp = payload.get("created_at") or payload.get("updated_at") or payload.get("observed_at")
        if isinstance(timestamp, str):
            metadata["timestamp"] = MarketReplayRunner._normalize_timestamp(timestamp)
        source_refs = []
        for key in ("source_packet_refs", "social_context_refs", "market_context_refs", "source_refs"):
            values = payload.get(key) or []
            source_refs.extend(str(item) for item in values)
        if source_refs:
            metadata["source_refs"] = list(dict.fromkeys(source_refs))
        next_review_at = payload.get("next_review_at") or (payload_metadata.get("next_review_at") if isinstance(payload_metadata, dict) else None)
        if next_review_at is not None:
            metadata["next_review_at"] = utc_isoformat(next_review_at)
        resolution_policy_missing = payload.get("resolution_policy_missing")
        if resolution_policy_missing is None and isinstance(payload_metadata, dict):
            resolution_policy_missing = payload_metadata.get("resolution_policy_missing")
        if resolution_policy_missing is not None:
            metadata["resolution_policy_missing"] = bool(resolution_policy_missing)
        return metadata

    @staticmethod
    def _payload_metadata(payload: dict[str, Any], timestamp: datetime, *, source: str) -> dict[str, Any]:
        result = {"source": source, "timestamp": timestamp.isoformat()}
        payload_metadata = payload.get("metadata")
        if isinstance(payload_metadata, dict) and payload_metadata:
            result["source"] = payload_metadata.get("source")
        content_hash = payload.get("content_hash")
        if isinstance(content_hash, str) and content_hash:
            result["content_hash"] = content_hash
        source_refs = []
        for key in ("source_packet_refs", "social_context_refs", "market_context_refs", "source_refs"):
            values = payload.get(key) or []
            source_refs.extend(str(item) for item in values)
        if source_refs:
            result["source_refs"] = list(dict.fromkeys(source_refs))
        next_review_at = payload.get("next_review_at") or (payload_metadata.get("next_review_at") if isinstance(payload_metadata, dict) else None)
        if next_review_at is not None:
            result["next_review_at"] = utc_isoformat(next_review_at)
        resolution_policy_missing = payload.get("resolution_policy_missing")
        if resolution_policy_missing is None and isinstance(payload_metadata, dict):
            resolution_policy_missing = payload_metadata.get("resolution_policy_missing")
        if resolution_policy_missing is not None:
            result["resolution_policy_missing"] = bool(resolution_policy_missing)
        return result

    @staticmethod
    def _same_readiness(original: ExecutionReadiness | None, replay: ExecutionReadiness | None) -> bool:
        return MarketReplayRunner._readiness_signature(original) == MarketReplayRunner._readiness_signature(replay)

    @staticmethod
    def _readiness_signature(packet: ExecutionReadiness | None) -> dict[str, Any] | None:
        if packet is None:
            return None
        payload = packet.model_dump(mode="json")
        return {
            "market_id": payload.get("market_id"),
            "venue": payload.get("venue"),
            "decision_action": payload.get("decision_action"),
            "side": payload.get("side"),
            "size_usd": payload.get("size_usd"),
            "limit_price": payload.get("limit_price"),
            "max_slippage_bps": payload.get("max_slippage_bps"),
            "confidence": payload.get("confidence"),
            "edge_after_fees_bps": payload.get("edge_after_fees_bps"),
            "risk_checks_passed": payload.get("risk_checks_passed"),
            "manual_review_required": payload.get("manual_review_required"),
            "ready_to_execute": payload.get("ready_to_execute"),
            "ready_to_paper": payload.get("ready_to_paper"),
            "ready_to_live": payload.get("ready_to_live"),
            "can_materialize_trade_intent": payload.get("can_materialize_trade_intent"),
            "blocked_reasons": payload.get("blocked_reasons") or [],
            "no_trade_reasons": payload.get("no_trade_reasons") or [],
            "route": payload.get("route"),
        }

    @staticmethod
    def _normalize_timestamp(timestamp: str) -> str:
        if timestamp.endswith("Z"):
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).isoformat()
        return datetime.fromisoformat(timestamp).isoformat()


class ReplayPostmortem(BaseModel):
    schema_version: str = "v1"
    postmortem_id: str = Field(default_factory=lambda: f"replaypm_{uuid4().hex[:12]}")
    run_id: str
    replay_id: str
    same_forecast: bool = False
    same_recommendation: bool = False
    same_decision: bool = False
    same_execution_readiness: bool = False
    same_execution_projection: bool | None = None
    drift_count: int = 0
    differences: list[str] = Field(default_factory=list)
    recommendation: str = "review"
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_replay_postmortem(report: ReplayReport) -> ReplayPostmortem:
    same_execution_projection = None
    if report.original_execution_projection is not None or report.replay_execution_projection is not None:
        same_execution_projection = execution_projection_signature(report.original_execution_projection) == execution_projection_signature(
            report.replay_execution_projection
        )
    differences = list(report.differences)
    drift_count = len(differences)
    notes = []
    if report.same_forecast and report.same_recommendation and report.same_decision and report.same_execution_readiness:
        notes.append("replay_stable")
    if same_execution_projection is False:
        notes.append("execution_projection_drift")
    if "execution_readiness" in differences:
        notes.append("execution_readiness_drift")
    if "recommendation.action" in differences or "decision.action" in differences:
        notes.append("decision_surface_drift")
    surface_context = report.metadata.get("original_report_context") if isinstance(report.metadata, dict) else None
    if isinstance(surface_context, dict):
        if surface_context.get("order_trace_audit"):
            notes.append("order_trace_audit_present")
        if surface_context.get("research_bridge"):
            notes.append("research_bridge_present")
        if surface_context.get("feed_surface"):
            notes.append("feed_surface_present")
            feed_surface = surface_context.get("feed_surface")
            if isinstance(feed_surface, dict):
                if feed_surface.get("supports_websocket") is True:
                    notes.append("feed_surface_supports_websocket")
                if feed_surface.get("supports_rtds") is True:
                    notes.append("feed_surface_supports_rtds")
        if surface_context.get("taxonomy"):
            notes.append(f"taxonomy:{surface_context['taxonomy']}")
        elif surface_context.get("taxonomy_counts"):
            notes.append("taxonomy_counts_present")
        if surface_context.get("execution_filter_reason_codes"):
            notes.append("execution_filter_reason_codes_present")
        execution_surface = surface_context.get("execution_surface")
        if isinstance(execution_surface, dict):
            planning_bucket = execution_surface.get("planning_bucket")
            execution_equivalent = execution_surface.get("execution_equivalent")
            execution_like = execution_surface.get("execution_like")
            if planning_bucket:
                notes.append(f"execution_surface:{planning_bucket}")
            if execution_equivalent is True:
                notes.append("execution_surface_role:execution-equivalent")
            elif execution_like is True:
                notes.append("execution_surface_role:execution-like")
    recommendation = "ok" if drift_count == 0 else "review"
    if same_execution_projection is False and drift_count <= 1:
        recommendation = "inspect_projection"
    metadata = dict(report.metadata)
    if isinstance(surface_context, dict) and surface_context:
        metadata["surface_context"] = surface_context
    return ReplayPostmortem(
        run_id=report.run_id,
        replay_id=report.replay_id,
        same_forecast=report.same_forecast,
        same_recommendation=report.same_recommendation,
        same_decision=report.same_decision,
        same_execution_readiness=report.same_execution_readiness,
        same_execution_projection=same_execution_projection,
        drift_count=drift_count,
        differences=differences,
        recommendation=recommendation,
        notes=notes,
        metadata=metadata,
    )
