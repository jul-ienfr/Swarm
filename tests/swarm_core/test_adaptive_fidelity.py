from swarm_core.adaptive_fidelity import AdaptiveFidelityPlanner, FidelityMode, FidelityRequest


def test_adaptive_fidelity_prefers_low_for_preview_goals() -> None:
    planner = AdaptiveFidelityPlanner()
    plan = planner.plan(
        FidelityRequest(
            goal="quick preview of the run",
            quality_priority=0.2,
            requested_population=64,
            requested_rounds=4,
            requested_parallelism=8,
            max_population=128,
        )
    )

    assert plan.mode == FidelityMode.low
    assert plan.population_size == 64
    assert plan.rounds == 4
    assert plan.parallelism == 8


def test_adaptive_fidelity_prefers_high_for_strategic_goals() -> None:
    planner = AdaptiveFidelityPlanner()
    plan = planner.plan(
        FidelityRequest(
            goal="strategic decision for the final hybrid run",
            quality_priority=0.95,
            max_population=800,
        )
    )

    assert plan.mode in {FidelityMode.high, FidelityMode.exhaustive}
    assert plan.population_size >= 128
    assert plan.rounds >= 3
    assert plan.parallelism >= 8

