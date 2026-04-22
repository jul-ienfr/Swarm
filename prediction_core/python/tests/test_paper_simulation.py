from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from prediction_core.paper import PaperTradeFill, PaperTradeSimulation, PaperTradeStatus


def test_paper_simulation_derives_average_fill_price_and_activity_state() -> None:
    simulation = PaperTradeSimulation(
        run_id="run-123",
        market_id="market-xyz",
        status=PaperTradeStatus.filled,
        requested_quantity=2.0,
        filled_quantity=2.0,
        gross_notional=0.84,
        fills=[
            PaperTradeFill(
                trade_id="trade-1",
                run_id="run-123",
                market_id="market-xyz",
                requested_quantity=2.0,
                filled_quantity=2.0,
                fill_price=0.42,
                gross_notional=0.84,
            )
        ],
    )

    assert simulation.average_fill_price == 0.42
    assert simulation.fill_count == 1
    assert simulation.is_active is True
    assert simulation.settlement_status == "simulated_settled"


def test_paper_simulation_marks_skipped_trades_as_not_settled() -> None:
    simulation = PaperTradeSimulation(
        run_id="run-124",
        market_id="market-abc",
        status=PaperTradeStatus.skipped,
    )

    assert simulation.is_active is False
    assert simulation.settlement_status == "not_settled"
