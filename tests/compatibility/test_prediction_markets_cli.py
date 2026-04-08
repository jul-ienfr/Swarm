from __future__ import annotations

from typer.testing import CliRunner

import main
import swarm_mcp


def _fake_payload(run_id: str = "pm_run_demo") -> dict:
    return {
        "run_id": run_id,
        "descriptor": {"market_id": "m1", "question": "Will it happen?"},
        "snapshot": {"midpoint_yes": 0.57},
        "forecast": {"probability_yes": 0.63},
        "recommendation": {"action": "bet", "edge": 0.06, "rationale": "Edge is positive."},
    }


def _fake_runs_payload() -> dict:
    return {
        "count": 1,
        "limit": 20,
        "runs": [
            {
                "run_id": "pm_run_recent",
                "market_id": "m1",
                "venue": "polymarket",
                "manifest_path": "/tmp/demo/manifest.json",
                "mode": "advise",
                "created_at": "2026-04-07T00:00:00Z",
                "updated_at": None,
                "metadata": {},
            }
        ],
    }


def test_prediction_markets_cli_advise_and_replay(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("main.advise_market_sync", lambda **kwargs: _fake_payload("pm_run_advise"))
    monkeypatch.setattr(
        "main.replay_market_run_sync",
        lambda run_id, **kwargs: {**_fake_payload(run_id), "replay_postmortem": {"run_id": run_id, "recommendation": "ok"}},
    )
    monkeypatch.setattr(
        "main.replay_market_postmortem_sync",
        lambda run_id, **kwargs: {"run_id": run_id, "exists": True, "replay_postmortem": {"run_id": run_id, "recommendation": "ok"}},
    )

    advise = runner.invoke(main.app, ["prediction-markets", "advise", "--slug", "demo-election-market", "--json"])
    replay = runner.invoke(main.app, ["prediction-markets", "replay", "pm_run_advise", "--json"])
    replay_postmortem = runner.invoke(main.app, ["prediction-markets", "replay-postmortem", "pm_run_advise", "--json"])

    assert advise.exit_code == 0
    assert '"run_id": "pm_run_advise"' in advise.stdout
    assert replay.exit_code == 0
    assert '"run_id": "pm_run_advise"' in replay.stdout
    assert '"replay_postmortem"' in replay.stdout
    assert replay_postmortem.exit_code == 0
    assert '"recommendation": "ok"' in replay_postmortem.stdout


def test_prediction_markets_cli_paper(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        "main.paper_trade_market_sync",
        lambda **kwargs: {**_fake_payload("pm_run_paper"), "paper_trade": {"trade_id": "paper_1", "size": 25.0}},
    )

    result = runner.invoke(main.app, ["polymarket", "paper", "--slug", "demo-election-market", "--stake", "25", "--json"])

    assert result.exit_code == 0
    assert '"trade_id": "paper_1"' in result.stdout


def test_prediction_markets_cli_microstructure_and_postmortems(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        "main.shadow_trade_market_sync",
        lambda **kwargs: {
            "run_id": "pm_run_shadow",
            "descriptor": {"market_id": "m1", "question": "Will it happen?"},
            "shadow_execution": {"shadow_id": "shadow_1"},
            "shadow_postmortem": {"shadow_id": "shadow_1", "paper_trade_postmortem": {"fill_rate": 1.0}},
        },
    )
    monkeypatch.setattr(
        "main.simulate_market_slippage_sync",
        lambda **kwargs: {
            "run_id": "pm_run_slippage",
            "descriptor": {"market_id": "m1", "question": "Will it happen?"},
            "slippage_report": {"report_id": "slip_1"},
            "slippage_postmortem": {"report_id": "slip_1", "recommendation": "hold"},
        },
    )
    monkeypatch.setattr(
        "main.simulate_microstructure_lab_sync",
        lambda **kwargs: {
            "run_id": "pm_run_micro",
            "descriptor": {"market_id": "m1", "question": "Will it happen?"},
            "microstructure_report": {"report_id": "micro_1"},
            "microstructure_postmortem": {"report_id": "micro_1", "recommendation": "hold"},
        },
    )

    shadow = runner.invoke(main.app, ["prediction-markets", "shadow", "--slug", "demo-election-market", "--json"])
    slippage = runner.invoke(main.app, ["prediction-markets", "slippage", "--slug", "demo-election-market", "--requested-notional", "10", "--json"])
    microstructure = runner.invoke(
        main.app,
        [
            "prediction-markets",
            "microstructure",
            "--slug",
            "demo-election-market",
            "--requested-quantity",
            "1.5",
            "--json",
        ],
    )

    assert shadow.exit_code == 0
    assert '"shadow_postmortem"' in shadow.stdout
    assert slippage.exit_code == 0
    assert '"slippage_postmortem"' in slippage.stdout
    assert microstructure.exit_code == 0
    assert '"microstructure_postmortem"' in microstructure.stdout


def test_prediction_markets_cli_runs(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("main._collect_prediction_market_runs", lambda **kwargs: _fake_runs_payload())

    result = runner.invoke(main.app, ["prediction-markets", "runs", "--json"])

    assert result.exit_code == 0
    assert '"run_id": "pm_run_recent"' in result.stdout


def test_prediction_markets_mcp_tools(monkeypatch) -> None:
    monkeypatch.setattr("swarm_mcp.advise_market_sync", lambda **kwargs: _fake_payload("pm_run_mcp"))
    monkeypatch.setattr("swarm_mcp.paper_trade_market_sync", lambda **kwargs: {**_fake_payload("pm_run_paper"), "paper_trade": {"trade_id": "paper_2"}})
    monkeypatch.setattr(
        "swarm_mcp.simulate_microstructure_lab_sync",
        lambda **kwargs: {
            "run_id": "pm_run_micro",
            "descriptor": {"market_id": "m1", "question": "Will it happen?"},
            "microstructure_report": {"report_id": "micro_1"},
            "microstructure_postmortem": {"report_id": "micro_1", "recommendation": "hold"},
        },
    )
    monkeypatch.setattr(
        "swarm_mcp.replay_market_run_sync",
        lambda run_id, **kwargs: {**_fake_payload(run_id), "replay_postmortem": {"run_id": run_id, "recommendation": "ok"}},
    )
    monkeypatch.setattr(
        "swarm_mcp.replay_market_postmortem_sync",
        lambda run_id, **kwargs: {"run_id": run_id, "exists": True, "replay_postmortem": {"run_id": run_id, "recommendation": "ok"}},
    )
    monkeypatch.setattr("swarm_mcp._prediction_markets_runs", lambda limit=20: {"ok": True, "result": _fake_runs_payload()})

    advise_payload = swarm_mcp.prediction_markets_advise(slug="demo-election-market")
    paper_payload = swarm_mcp.prediction_markets_paper(slug="demo-election-market")
    replay_payload = swarm_mcp.prediction_markets_replay("pm_run_demo")
    replay_postmortem_payload = swarm_mcp.prediction_markets_replay_postmortem("pm_run_demo")
    runs_payload = swarm_mcp.prediction_markets_runs()

    assert advise_payload["ok"] is True
    assert advise_payload["result"]["run_id"] == "pm_run_mcp"
    assert paper_payload["ok"] is True
    assert paper_payload["result"]["paper_trade"]["trade_id"] == "paper_2"
    micro_payload = swarm_mcp.prediction_markets_microstructure(slug="demo-election-market", requested_quantity=1.5)
    assert micro_payload["ok"] is True
    assert micro_payload["result"]["microstructure_postmortem"]["report_id"] == "micro_1"
    assert replay_payload["ok"] is True
    assert replay_payload["result"]["run_id"] == "pm_run_demo"
    assert replay_payload["result"]["replay_postmortem"]["recommendation"] == "ok"
    assert replay_postmortem_payload["ok"] is True
    assert replay_postmortem_payload["result"]["replay_postmortem"]["recommendation"] == "ok"
    assert runs_payload["ok"] is True
    assert runs_payload["result"]["runs"][0]["run_id"] == "pm_run_recent"
