from __future__ import annotations

from pathlib import Path

from prediction_markets import timesfm_sidecar


def _history_points(count: int) -> list[dict[str, float | int]]:
    return [
        {
            "timestamp": 1712534400 + (index * 3600),
            "price": round(0.42 + (index * 0.008), 6),
        }
        for index in range(count)
    ]


def test_timesfm_vendor_snapshot_metadata_is_present() -> None:
    assert timesfm_sidecar.TIMESFM_VENDOR_ROOT.exists()
    assert (timesfm_sidecar.TIMESFM_VENDOR_ROOT / "UPSTREAM.md").exists()
    assert (timesfm_sidecar.TIMESFM_VENDOR_ROOT / "PATCHES.md").exists()
    assert (timesfm_sidecar.TIMESFM_VENDOR_SRC / "timesfm" / "__init__.py").exists()


def test_timesfm_fixture_backend_returns_deterministic_ready_microstructure_lane() -> None:
    bundle = timesfm_sidecar.run_timesfm_sidecar({
        "run_id": "run-timesfm",
        "market_id": "market-timesfm",
        "venue": "polymarket",
        "question": "Will the fixture backend remain deterministic?",
        "request_mode": "predict_deep",
        "timesfm_mode": "auto",
        "timesfm_lanes": ["microstructure", "event_probability"],
        "history": _history_points(40),
        "midpoint_yes": 0.56,
        "yes_price": 0.56,
        "spread_bps": 120,
        "depth_near_touch": 900,
        "force_fixture_backend": True,
    })

    assert bundle["sidecar_name"] == "timesfm_sidecar"
    assert bundle["health"]["status"] == "healthy"
    assert bundle["selected_lane"] == "microstructure"
    assert bundle["lanes"]["microstructure"]["status"] == "ready"
    assert bundle["lanes"]["microstructure"]["basis"] == "timesfm_microstructure"
    assert bundle["lanes"]["microstructure"]["probability_yes"] is not None
    assert bundle["lanes"]["microstructure"]["metadata"]["features_used"]
    assert bundle["lanes"]["microstructure"]["metadata"]["content_hash"]
    assert bundle["metadata"]["content_hash"]
    assert bundle["lanes"]["event_probability"]["status"] == "ready"


def test_timesfm_auto_mode_degrades_cleanly_when_vendor_snapshot_is_missing(monkeypatch) -> None:
    missing_vendor_src = Path("/tmp/timesfm-vendor-missing-for-test")
    monkeypatch.setattr(timesfm_sidecar, "TIMESFM_VENDOR_SRC", missing_vendor_src)

    bundle = timesfm_sidecar.run_timesfm_sidecar({
        "run_id": "run-timesfm-missing",
        "market_id": "market-timesfm-missing",
        "venue": "polymarket",
        "question": "Will missing vendor snapshots degrade cleanly?",
        "request_mode": "predict_deep",
        "timesfm_mode": "auto",
        "timesfm_lanes": ["microstructure"],
        "history": _history_points(20),
        "midpoint_yes": 0.54,
        "yes_price": 0.54,
    })

    assert bundle["health"]["status"] == "degraded"
    assert bundle["health"]["healthy"] is False
    assert bundle["lanes"]["microstructure"]["status"] == "abstained"
    assert "vendor_snapshot_missing" in bundle["lanes"]["microstructure"]["reasons"]


def test_timesfm_vendor_backend_uses_upstream_forecast_when_model_is_available(monkeypatch) -> None:
    class FakeModel:
        def forecast(self, horizon: int, inputs: list[list[float]]):
            assert horizon == 24
            assert len(inputs) == 1
            points = [[0.51, 0.55, 0.61]]
            quantiles = [[
                [0.45, 0.46, 0.47, 0.48, 0.49, 0.51, 0.53, 0.56, 0.59, 0.62],
                [0.47, 0.48, 0.49, 0.50, 0.52, 0.55, 0.57, 0.59, 0.61, 0.64],
                [0.50, 0.51, 0.52, 0.54, 0.57, 0.61, 0.64, 0.67, 0.70, 0.73],
            ]]
            return points, quantiles

    monkeypatch.setattr(
        timesfm_sidecar,
        "_vendor_import_status",
        lambda: timesfm_sidecar._VendorImportStatus(
            available=True,
            backend="vendor_torch_candidate",
            dependency_status="vendor_import_available",
            issues=[],
        ),
    )
    monkeypatch.setattr(
        timesfm_sidecar,
        "_load_vendor_model",
        lambda: (
            FakeModel(),
            timesfm_sidecar._VendorModelSettings(model_id="local-timesfm", local_files_only=True),
        ),
    )

    bundle = timesfm_sidecar.run_timesfm_sidecar({
        "run_id": "run-timesfm-vendor",
        "market_id": "market-timesfm-vendor",
        "venue": "polymarket",
        "question": "Will the vendored backend be used?",
        "request_mode": "predict_deep",
        "timesfm_mode": "auto",
        "timesfm_lanes": ["microstructure"],
        "history": _history_points(40),
        "midpoint_yes": 0.56,
        "yes_price": 0.56,
    })

    assert bundle["health"]["status"] == "healthy"
    assert bundle["health"]["backend"] == "vendor_torch"
    assert bundle["lanes"]["microstructure"]["status"] == "ready"
    assert bundle["lanes"]["microstructure"]["probability_yes"] == 0.61
    assert bundle["lanes"]["microstructure"]["quantiles"]["p50"] == 0.61
    assert bundle["lanes"]["microstructure"]["metadata"]["vendor_model_id"] == "local-timesfm"
    assert bundle["lanes"]["microstructure"]["metadata"]["provenance"]["commit"] == timesfm_sidecar.TIMESFM_UPSTREAM_COMMIT


def test_timesfm_vendor_backend_abstains_cleanly_when_forecast_execution_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        timesfm_sidecar,
        "_vendor_import_status",
        lambda: timesfm_sidecar._VendorImportStatus(
            available=True,
            backend="vendor_torch_candidate",
            dependency_status="vendor_import_available",
            issues=[],
        ),
    )
    monkeypatch.setattr(
        timesfm_sidecar,
        "_load_vendor_model",
        lambda: (_ for _ in ()).throw(RuntimeError("weights unavailable")),
    )

    bundle = timesfm_sidecar.run_timesfm_sidecar({
        "run_id": "run-timesfm-vendor-fail",
        "market_id": "market-timesfm-vendor-fail",
        "venue": "polymarket",
        "question": "Will vendor forecast failures abstain cleanly?",
        "request_mode": "predict_deep",
        "timesfm_mode": "auto",
        "timesfm_lanes": ["microstructure"],
        "history": _history_points(40),
        "midpoint_yes": 0.56,
        "yes_price": 0.56,
    })

    assert bundle["health"]["status"] == "degraded"
    assert bundle["health"]["healthy"] is False
    assert bundle["lanes"]["microstructure"]["status"] == "abstained"
    assert "vendor_forecast_failed:RuntimeError" in bundle["lanes"]["microstructure"]["reasons"]
