from swarm_core.deliberation_workbench_tasks import build_default_workbench_task_plan


def test_workbench_task_plan_covers_core_pipeline() -> None:
    plan = build_default_workbench_task_plan(workbench_id="wb_demo")

    labels = [task.label for task in plan.tasks]
    assert "normalize_inputs" in labels
    assert "generate_profiles" in labels
    assert "build_graph" in labels
    assert "build_visuals" in labels
