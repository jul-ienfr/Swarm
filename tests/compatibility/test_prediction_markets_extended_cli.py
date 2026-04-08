from __future__ import annotations

import json
from types import SimpleNamespace

from typer.testing import CliRunner

import main
import swarm_mcp
from prediction_markets import VenueHealthReport, MarketStreamHealth, VenueName
from prediction_markets.compat import venue_health_sync


def _fake_extended_payload(run_id: str, key: str) -> dict:
    return {
        "run_id": run_id,
        "descriptor": {"market_id": "m1", "question": "Will it happen?"},
        key: {"id": f"{key}_1"},
    }


def test_prediction_markets_extended_cli_commands(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("main.assess_market_risk_sync", lambda **kwargs: {"run_id": "pm_risk", "descriptor": {"market_id": "m1", "question": "Q?"}, "risk_report": {"risk_id": "risk_1"}})
    monkeypatch.setattr("main.allocate_market_sync", lambda **kwargs: {"run_id": "pm_alloc", "descriptor": {"market_id": "m1", "question": "Q?"}, "allocation": {"allocation_id": "alloc_1"}})
    monkeypatch.setattr("main.shadow_trade_market_sync", lambda **kwargs: {"run_id": "pm_shadow", "descriptor": {"market_id": "m1", "question": "Q?"}, "shadow_execution": {"shadow_id": "shadow_1"}})
    monkeypatch.setattr("main.live_execute_market_sync", lambda **kwargs: {"run_id": "pm_live", "descriptor": {"market_id": "m1", "question": "Q?"}, "live_execution": {"execution_id": "lexec_1"}})
    monkeypatch.setattr("main.market_execution_sync", lambda **kwargs: {"run_id": "pm_mexec", "descriptor": {"market_id": "m1", "question": "Q?"}, "market_execution": {"report_id": "mexec_1"}})
    monkeypatch.setattr("main.research_market_sync", lambda **kwargs: {"run_id": "pm_research", "descriptor": {"market_id": "m1", "question": "Q?"}, "research_synthesis": {"synthesis_id": "rsyn_1"}})
    monkeypatch.setattr("main.simulate_market_slippage_sync", lambda **kwargs: {"run_id": "pm_slippage", "descriptor": {"market_id": "m1", "question": "Q?"}, "slippage_report": {"report_id": "slip_1"}})
    monkeypatch.setattr("main.simulate_microstructure_lab_sync", lambda **kwargs: {"run_id": "pm_micro", "descriptor": {"market_id": "m1", "question": "Q?"}, "microstructure_report": {"report_id": "micro_1"}, "microstructure_postmortem": {"report_id": "micro_1"}})
    monkeypatch.setattr("main.analyze_market_comments_sync", lambda **kwargs: {"run_id": "pm_comment", "descriptor": {"market_id": "m1", "question": "Q?"}, "comment_intel": {"report_id": "mci_1"}})
    monkeypatch.setattr("main.guard_market_manipulation_sync", lambda **kwargs: {"run_id": "pm_guard", "descriptor": {"market_id": "m1", "question": "Q?"}, "manipulation_guard": {"guard_id": "mguard_1"}})
    monkeypatch.setattr("main.build_market_graph_sync", lambda **kwargs: {"run_id": "pm_graph", "descriptor": {"market_id": "m1", "question": "Q?"}, "market_graph": {"graph_id": "graph_1"}})
    monkeypatch.setattr("main.cross_venue_intelligence_sync", lambda **kwargs: {"run_id": "pm_cross", "descriptor": {"market_id": "m1", "question": "Q?"}, "cross_venue": {"report_id": "cross_1"}})
    monkeypatch.setattr("main.multi_venue_paper_sync", lambda **kwargs: {"run_id": "pm_mvpaper", "descriptor": {"market_id": "m1", "question": "Q?"}, "multi_venue_paper": {"report_id": "mvpaper_1"}})
    monkeypatch.setattr("main.monitor_market_spreads_sync", lambda **kwargs: {"run_id": "pm_spread", "descriptor": {"market_id": "m1", "question": "Q?"}, "spread_monitor": {"report_id": "spread_1"}})
    monkeypatch.setattr("main.assess_market_arbitrage_sync", lambda **kwargs: {"run_id": "pm_arb", "descriptor": {"market_id": "m1", "question": "Q?"}, "arbitrage_lab": {"report_id": "arb_1"}})
    monkeypatch.setattr("main.open_market_stream_sync", lambda **kwargs: {"stream_id": "stream_1", "descriptor": {"market_id": "m1", "question": "Q?"}, "stream_summary": {"stream_id": "stream_1"}})
    monkeypatch.setattr("main.market_stream_summary_sync", lambda stream_id, **kwargs: {"stream_id": stream_id, "stream_summary": {"stream_id": stream_id}})
    monkeypatch.setattr("main.market_stream_health_sync", lambda stream_id, **kwargs: {"stream_id": stream_id, "stream_health": {"stream_id": stream_id, "healthy": True}})
    monkeypatch.setattr("main.stream_collect_sync", lambda **kwargs: {"stream_collection": {"report_id": "streamctl_1", "cache_hit_count": 2, "batch_count": 2}})
    monkeypatch.setattr("main.ingest_worldmonitor_sidecar_sync", lambda source, **kwargs: {"run_id": "pm_world", "descriptor": {"market_id": "m1", "question": "Q?"}, "worldmonitor_sidecar": {"bundle_id": "world_1", "source": source}})
    monkeypatch.setattr("main.ingest_twitter_watcher_sidecar_sync", lambda source, **kwargs: {"run_id": "pm_twitter", "descriptor": {"market_id": "m1", "question": "Q?"}, "twitter_watcher_sidecar": {"bundle_id": "twitter_1", "source": source}})
    monkeypatch.setattr("main.market_events_sync", lambda **kwargs: {"run_id": "pm_events", "descriptor": {"market_id": "m1", "question": "Q?"}, "market_events": [{"market_id": "m1"}]})
    monkeypatch.setattr("main.market_positions_sync", lambda **kwargs: {"run_id": "pm_positions", "descriptor": {"market_id": "m1", "question": "Q?"}, "market_positions": [{"market_id": "m1", "quantity": 1.0}]})
    monkeypatch.setattr(
        "main.additional_venues_catalog_sync",
        lambda **kwargs: {
            "run_id": "pm_venues",
            "additional_venues_matrix": {
                "profiles": [
                    {
                        "venue": "manifold",
                        "execution_kind": "execution-like",
                        "manual_review_required": True,
                    }
                ]
            },
        },
    )
    monkeypatch.setattr("main.reconcile_market_run_sync", lambda run_id, **kwargs: {"run_id": run_id, "descriptor": {"market_id": "m1", "question": "Q?"}, "reconciliation": {"reconciliation_id": "recon_1"}})

    assert runner.invoke(main.app, ["prediction-markets", "risk", "--slug", "demo-election-market", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "allocate", "--slug", "demo-election-market", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "shadow", "--slug", "demo-election-market", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "live", "--slug", "demo-election-market", "--dry-run", "--authorized", "--compliance-approved", "--scope", "prediction_markets:execute", "--require-human-approval-before-live", "--human-approved", "--human-approval-actor", "operator", "--human-approval-reason", "checked", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "market-execution", "--slug", "demo-election-market", "--dry-run", "--authorized", "--compliance-approved", "--scope", "prediction_markets:execute", "--require-human-approval-before-live", "--human-approved", "--human-approval-actor", "operator", "--human-approval-reason", "checked", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "research", "--slug", "demo-election-market", "--evidence", "demo", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "slippage", "--slug", "demo-election-market", "--requested-notional", "10", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "microstructure", "--slug", "demo-election-market", "--requested-quantity", "1.5", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "comment-intel", "--slug", "demo-election-market", "--comment", "demo", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "manipulation-guard", "--slug", "demo-election-market", "--comment", "demo", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "graph", "--slug", "demo-election-market", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "cross-venue", "--slug", "demo-election-market", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "multi-venue-paper", "--slug", "demo-election-market", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "spread-monitor", "--slug", "demo-election-market", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "arbitrage-lab", "--slug", "demo-election-market", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "stream-open", "--slug", "demo-election-market", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "stream-summary", "stream_1", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "stream-health", "stream_1", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "stream-collect", "--market-id", "demo-election-market", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "worldmonitor", "payload.json", "--slug", "demo-election-market", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "twitter-watcher", "payload.json", "--slug", "demo-election-market", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "events", "--slug", "demo-election-market", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "positions", "--slug", "demo-election-market", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "venues", "--query", "btc", "--json"]).exit_code == 0
    assert runner.invoke(main.app, ["prediction-markets", "reconcile", "pm_shadow", "--json"]).exit_code == 0


def test_prediction_markets_cli_surfaces_execution_audit_fields(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setattr(
        "main.market_execution_sync",
        lambda **kwargs: {
            "run_id": "pm_mexec",
            "descriptor": {"market_id": "m1", "question": "Q?"},
            "market_execution": {
                "report_id": "mexec_1",
                "execution_kind": "execution-equivalent",
                "manual_review_required": True,
                "order_trace_audit": {"trace_id": "trace_1", "events": ["place", "cancel"]},
            },
        },
    )

    result = runner.invoke(
        main.app,
        ["prediction-markets", "market-execution", "--slug", "demo-election-market", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["market_execution"]["execution_kind"] == "execution-equivalent"
    assert payload["market_execution"]["manual_review_required"] is True
    assert payload["market_execution"]["order_trace_audit"]["trace_id"] == "trace_1"


def test_prediction_markets_cli_surfaces_execution_like_and_reviewable_venues(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setattr(
        "main.additional_venues_catalog_sync",
        lambda **kwargs: {
            "run_id": "pm_venues",
            "additional_venues_matrix": {
                "profiles": [
                    {
                        "venue": "manifold",
                        "execution_kind": "execution-like",
                        "manual_review_required": True,
                    }
                ]
            },
        },
    )

    result = runner.invoke(
        main.app,
        ["prediction-markets", "venues", "--query", "btc", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    profile = payload["additional_venues_matrix"]["profiles"][0]
    assert profile["execution_kind"] == "execution-like"
    assert profile["manual_review_required"] is True


def test_prediction_markets_extended_mcp_tools(monkeypatch) -> None:
    monkeypatch.setattr("swarm_mcp.assess_market_risk_sync", lambda **kwargs: {"run_id": "pm_risk", "risk_report": {"risk_id": "risk_1"}})
    monkeypatch.setattr("swarm_mcp.allocate_market_sync", lambda **kwargs: {"run_id": "pm_alloc", "allocation": {"allocation_id": "alloc_1"}})
    monkeypatch.setattr("swarm_mcp.shadow_trade_market_sync", lambda **kwargs: {"run_id": "pm_shadow", "shadow_execution": {"shadow_id": "shadow_1"}})
    monkeypatch.setattr("swarm_mcp.live_execute_market_sync", lambda **kwargs: {"run_id": "pm_live", "live_execution": {"execution_id": "lexec_1"}})
    monkeypatch.setattr("swarm_mcp.market_execution_sync", lambda **kwargs: {"run_id": "pm_mexec", "market_execution": {"report_id": "mexec_1"}})
    monkeypatch.setattr("swarm_mcp.research_market_sync", lambda **kwargs: {"run_id": "pm_research", "research_synthesis": {"synthesis_id": "rsyn_1"}})
    monkeypatch.setattr("swarm_mcp.simulate_market_slippage_sync", lambda **kwargs: {"run_id": "pm_slippage", "slippage_report": {"report_id": "slip_1"}})
    monkeypatch.setattr("swarm_mcp.simulate_microstructure_lab_sync", lambda **kwargs: {"run_id": "pm_micro", "microstructure_report": {"report_id": "micro_1"}, "microstructure_postmortem": {"report_id": "micro_1"}})
    monkeypatch.setattr("swarm_mcp.analyze_market_comments_sync", lambda **kwargs: {"run_id": "pm_comment", "comment_intel": {"report_id": "mci_1"}})
    monkeypatch.setattr("swarm_mcp.guard_market_manipulation_sync", lambda **kwargs: {"run_id": "pm_guard", "manipulation_guard": {"guard_id": "mguard_1"}})
    monkeypatch.setattr("swarm_mcp.build_market_graph_sync", lambda **kwargs: {"run_id": "pm_graph", "market_graph": {"graph_id": "graph_1"}})
    monkeypatch.setattr("swarm_mcp.cross_venue_intelligence_sync", lambda **kwargs: {"run_id": "pm_cross", "cross_venue": {"report_id": "cross_1"}})
    monkeypatch.setattr("swarm_mcp.multi_venue_paper_sync", lambda **kwargs: {"run_id": "pm_mvpaper", "multi_venue_paper": {"report_id": "mvpaper_1"}})
    monkeypatch.setattr("swarm_mcp.monitor_market_spreads_sync", lambda **kwargs: {"run_id": "pm_spread", "spread_monitor": {"report_id": "spread_1"}})
    monkeypatch.setattr("swarm_mcp.assess_market_arbitrage_sync", lambda **kwargs: {"run_id": "pm_arb", "arbitrage_lab": {"report_id": "arb_1"}})
    monkeypatch.setattr("swarm_mcp.open_market_stream_sync", lambda **kwargs: {"stream_id": "stream_1", "stream_summary": {"stream_id": "stream_1"}})
    monkeypatch.setattr("swarm_mcp.market_stream_summary_sync", lambda stream_id, **kwargs: {"stream_id": stream_id, "stream_summary": {"stream_id": stream_id}})
    monkeypatch.setattr("swarm_mcp.market_stream_health_sync", lambda stream_id, **kwargs: {"stream_id": stream_id, "stream_health": {"stream_id": stream_id, "healthy": True}})
    monkeypatch.setattr("swarm_mcp.stream_collect_sync", lambda **kwargs: {"stream_collection": {"report_id": "streamctl_1", "cache_hit_count": 2, "batch_count": 2}})
    monkeypatch.setattr("swarm_mcp.ingest_worldmonitor_sidecar_sync", lambda source, **kwargs: {"run_id": "pm_world", "worldmonitor_sidecar": {"bundle_id": "world_1", "source": source}})
    monkeypatch.setattr("swarm_mcp.ingest_twitter_watcher_sidecar_sync", lambda source, **kwargs: {"run_id": "pm_twitter", "twitter_watcher_sidecar": {"bundle_id": "twitter_1", "source": source}})
    monkeypatch.setattr("swarm_mcp.market_events_sync", lambda **kwargs: {"run_id": "pm_events", "market_events": [{"market_id": "m1"}]})
    monkeypatch.setattr("swarm_mcp.market_positions_sync", lambda **kwargs: {"run_id": "pm_positions", "market_positions": [{"market_id": "m1", "quantity": 1.0}]})
    monkeypatch.setattr(
        "swarm_mcp.additional_venues_catalog_sync",
        lambda **kwargs: {
            "run_id": "pm_venues",
            "additional_venues_matrix": {
                "profiles": [
                    {
                        "venue": "manifold",
                        "execution_kind": "execution-like",
                        "manual_review_required": True,
                    }
                ]
            },
        },
    )
    monkeypatch.setattr("swarm_mcp.reconcile_market_run_sync", lambda run_id, **kwargs: {"run_id": run_id, "reconciliation": {"reconciliation_id": "recon_1"}})

    assert swarm_mcp.prediction_markets_risk(slug="demo-election-market")["ok"] is True
    assert swarm_mcp.prediction_markets_allocate(slug="demo-election-market")["ok"] is True
    assert swarm_mcp.prediction_markets_shadow(slug="demo-election-market")["ok"] is True
    assert swarm_mcp.prediction_markets_live(slug="demo-election-market", dry_run=True, authorized=True, compliance_approved=True, scopes=["prediction_markets:execute"], require_human_approval_before_live=True, human_approval_passed=True, human_approval_actor="operator", human_approval_reason="checked")["ok"] is True
    assert swarm_mcp.prediction_markets_market_execution(slug="demo-election-market", dry_run=True, authorized=True, compliance_approved=True, scopes=["prediction_markets:execute"], require_human_approval_before_live=True, human_approval_passed=True, human_approval_actor="operator", human_approval_reason="checked")["ok"] is True
    assert swarm_mcp.prediction_markets_research(slug="demo-election-market", evidence=["demo"])["ok"] is True
    assert swarm_mcp.prediction_markets_slippage(slug="demo-election-market", requested_notional=10.0)["ok"] is True
    assert swarm_mcp.prediction_markets_microstructure(slug="demo-election-market", requested_quantity=1.5)["ok"] is True
    assert swarm_mcp.prediction_markets_comment_intel(slug="demo-election-market", comments=["demo"])["ok"] is True
    assert swarm_mcp.prediction_markets_manipulation_guard(slug="demo-election-market", comments=["demo"])["ok"] is True
    assert swarm_mcp.prediction_markets_graph(slug="demo-election-market")["ok"] is True
    assert swarm_mcp.prediction_markets_cross_venue(slug="demo-election-market")["ok"] is True
    assert swarm_mcp.prediction_markets_multi_venue_paper(slug="demo-election-market")["ok"] is True
    assert swarm_mcp.prediction_markets_spread_monitor(slug="demo-election-market")["ok"] is True
    assert swarm_mcp.prediction_markets_arbitrage_lab(slug="demo-election-market")["ok"] is True
    assert swarm_mcp.prediction_markets_stream_open(slug="demo-election-market")["ok"] is True
    assert swarm_mcp.prediction_markets_stream_summary("stream_1")["ok"] is True
    assert swarm_mcp.prediction_markets_stream_health("stream_1")["ok"] is True
    assert swarm_mcp.prediction_markets_stream_collect(market_ids=["demo-election-market"])["ok"] is True
    assert swarm_mcp.prediction_markets_worldmonitor("payload.json", slug="demo-election-market")["ok"] is True
    assert swarm_mcp.prediction_markets_twitter_watcher("payload.json", slug="demo-election-market")["ok"] is True
    assert swarm_mcp.prediction_markets_events(slug="demo-election-market")["ok"] is True
    assert swarm_mcp.prediction_markets_positions(slug="demo-election-market")["ok"] is True
    assert swarm_mcp.prediction_markets_venues(query="btc")["ok"] is True
    assert swarm_mcp.prediction_markets_reconcile("pm_shadow")["ok"] is True


def test_prediction_markets_mcp_surfaces_execution_audit_fields(monkeypatch) -> None:
    monkeypatch.setattr(
        "swarm_mcp.market_execution_sync",
        lambda **kwargs: {
            "run_id": "pm_mexec",
            "descriptor": {"market_id": "m1", "question": "Q?"},
            "market_execution": {
                "report_id": "mexec_1",
                "execution_kind": "execution-equivalent",
                "manual_review_required": True,
                "order_trace_audit": {"trace_id": "trace_1", "events": ["place", "cancel"]},
            },
        },
    )

    payload = swarm_mcp.prediction_markets_market_execution(slug="demo-election-market")

    assert payload["ok"] is True
    assert payload["result"]["market_execution"]["execution_kind"] == "execution-equivalent"
    assert payload["result"]["market_execution"]["manual_review_required"] is True
    assert payload["result"]["market_execution"]["order_trace_audit"]["trace_id"] == "trace_1"


def test_prediction_markets_mcp_surfaces_execution_like_and_reviewable_venues(monkeypatch) -> None:
    monkeypatch.setattr(
        "swarm_mcp.additional_venues_catalog_sync",
        lambda **kwargs: {
            "run_id": "pm_venues",
            "additional_venues_matrix": {
                "profiles": [
                    {
                        "venue": "manifold",
                        "execution_kind": "execution-like",
                        "manual_review_required": True,
                    }
                ]
            },
        },
    )

    payload = swarm_mcp.prediction_markets_venues(query="btc")

    assert payload["ok"] is True
    profile = payload["result"]["additional_venues_matrix"]["profiles"][0]
    assert profile["execution_kind"] == "execution-like"
    assert profile["manual_review_required"] is True


def test_prediction_markets_cli_accepts_deliberation_id_for_decision_packet(monkeypatch) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "main.load_deliberation_result",
        lambda deliberation_id: SimpleNamespace(
            deliberation_id=deliberation_id,
            decision_packet={"packet_kind": "decision_packet", "probability_estimate": 0.64},
        ),
    )

    def _fake_advise(**kwargs):
        captured.update(kwargs)
        return {"run_id": "pm_advise", "descriptor": {"market_id": "m1", "question": "Q?"}, "forecast": {"forecast_id": "f1"}}

    monkeypatch.setattr("main.advise_market_sync", _fake_advise)

    result = runner.invoke(
        main.app,
        ["prediction-markets", "advise", "--slug", "demo-election-market", "--deliberation-id", "delib_demo", "--json"],
    )

    assert result.exit_code == 0
    assert captured["decision_packet"] == {"packet_kind": "decision_packet", "probability_estimate": 0.64}


def test_prediction_markets_mcp_accepts_deliberation_id_for_decision_packet(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "swarm_mcp.load_deliberation_result",
        lambda deliberation_id: SimpleNamespace(
            deliberation_id=deliberation_id,
            decision_packet={"packet_kind": "decision_packet", "probability_estimate": 0.61},
        ),
    )

    def _fake_advise(**kwargs):
        captured.update(kwargs)
        return {"run_id": "pm_advise", "forecast": {"forecast_id": "f1"}}

    monkeypatch.setattr("swarm_mcp.advise_market_sync", _fake_advise)

    payload = swarm_mcp.prediction_markets_advise(
        slug="demo-election-market",
        deliberation_id="delib_demo",
    )

    assert payload["ok"] is True
    assert captured["decision_packet"] == {"packet_kind": "decision_packet", "probability_estimate": 0.61}


def test_venue_health_sync_aggregates_venue_and_stream_signals(monkeypatch) -> None:
    class FakeVenueClient:
        def health(self) -> VenueHealthReport:
            return VenueHealthReport(
                venue=VenueName.polymarket,
                backend_mode="live",
                healthy=False,
                message="api offline",
                details={"issues": ["api_error"], "transport": "http"},
            )

    class FakeStreamer:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def health(self, stream_id: str, *, stale_after_seconds: float = 3600.0) -> MarketStreamHealth:
            return MarketStreamHealth(
                stream_id=stream_id,
                market_id="pm_health",
                venue=VenueName.polymarket,
                healthy=False,
                stream_status="degraded",
                freshness_status="stale",
                message="stream stale",
                issues=["stream_stale"],
                issue_count=1,
                latest_sequence=1,
                event_count=1,
                poll_count=1,
                backend_mode="surrogate",
                metadata={"source": "test"},
            )

    monkeypatch.setattr("prediction_markets.compat.build_polymarket_client", lambda backend_mode=None: FakeVenueClient())
    monkeypatch.setattr("prediction_markets.compat.MarketStreamer", FakeStreamer)

    payload = venue_health_sync(venue=VenueName.polymarket, stream_id="stream_1")

    assert payload["healthy"] is False
    assert payload["venue_health"].healthy is False
    assert payload["stream_health"].healthy is False
    assert "api_error" in payload["issues"]
    assert "stream_stale" in payload["issues"]
