from swarm_core.run_health_monitor import RunHealthMonitor, RunHealthStatus


def test_run_health_monitor_marks_healthy_runs() -> None:
    monitor = RunHealthMonitor()
    report = monitor.evaluate(
        run_id="run-1",
        present_artifacts={"manifest", "result", "report", "graph"},
        elapsed_seconds=4.0,
        timeout_seconds=10.0,
        retries=0,
        errors=0,
        warnings=0,
    )

    assert report.status == RunHealthStatus.healthy
    assert report.score >= 0.9
    assert report.is_healthy is True


def test_run_health_monitor_blocks_missing_required_artifacts() -> None:
    monitor = RunHealthMonitor()
    report = monitor.evaluate(
        run_id="run-2",
        present_artifacts={"manifest", "graph"},
        elapsed_seconds=2.0,
        timeout_seconds=10.0,
        retries=1,
        errors=0,
        warnings=1,
    )

    assert report.status == RunHealthStatus.blocked
    assert report.is_blocked is True
    assert any(issue.code == "missing_required_artifacts" for issue in report.issues)

