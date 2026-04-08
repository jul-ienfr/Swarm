from swarm_core.cost_latency_control import (
    BudgetDecision,
    BudgetLimits,
    BudgetRequest,
    CostLatencyController,
)


def test_cost_latency_allows_within_budget() -> None:
    controller = CostLatencyController()
    report = controller.evaluate(
        BudgetRequest(
            requested_agents=16,
            requested_rounds=2,
            requested_parallelism=4,
            estimated_cost_units=4.0,
            estimated_latency_seconds=8.0,
        ),
        BudgetLimits(cost_units=10.0, latency_seconds=15.0, max_agents=32, max_rounds=4, max_parallelism=8),
    )

    assert report.decision == BudgetDecision.allow
    assert report.allowed is True
    assert report.adjusted_agents == 16
    assert report.adjusted_rounds == 2


def test_cost_latency_trims_over_budget_requests() -> None:
    controller = CostLatencyController()
    report = controller.evaluate(
        BudgetRequest(
            requested_agents=128,
            requested_rounds=6,
            requested_parallelism=8,
            estimated_cost_units=80.0,
            estimated_latency_seconds=60.0,
        ),
        BudgetLimits(cost_units=12.0, latency_seconds=18.0, max_agents=64, max_rounds=4, max_parallelism=8),
    )

    assert report.decision in {BudgetDecision.trim, BudgetDecision.allow}
    assert report.allowed is True
    assert report.adjusted_agents <= 64
    assert report.adjusted_rounds <= 4
    assert report.adjusted_cost_units <= 12.0 or "cost capped" in " ".join(report.reasons)

