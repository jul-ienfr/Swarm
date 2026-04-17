from pathlib import Path
import json
import subprocess
import time
from contextlib import contextmanager
from urllib.request import urlopen


REPO_ROOT = Path("/home/jul/swarm")


@contextmanager
def launch_node_server(command: list[str]):
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        yield process
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def wait_json(url: str) -> dict:
    deadline = time.time() + 10
    last_error = None
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - best effort loop
            last_error = exc
            time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {url}: {last_error}")


def test_swarm_dashboard_vendor_layout_exists() -> None:
    expected = [
        REPO_ROOT / "dashboard" / "index.html",
        REPO_ROOT / "dashboard" / "README.md",
        REPO_ROOT / "dashboard" / "swarm-ui" / "index.html",
        REPO_ROOT / "dashboard" / "swarm-ui" / "package.json",
        REPO_ROOT / "dashboard" / "swarm-ui-alt" / "index.html",
        REPO_ROOT / "dashboard" / "swarm-ui-alt" / "package.json",
    ]
    for path in expected:
        assert path.exists(), f"missing expected dashboard artifact: {path}"


def test_prediction_dashboard_vendor_layout_exists() -> None:
    expected = [
        REPO_ROOT / "subprojects" / "prediction" / "dashboard" / "index.html",
        REPO_ROOT / "subprojects" / "prediction" / "dashboard" / "README.md",
        REPO_ROOT / "subprojects" / "prediction" / "dashboard-ui" / "index.html",
        REPO_ROOT / "subprojects" / "prediction" / "dashboard-ui" / "package.json",
        REPO_ROOT / "subprojects" / "prediction" / "dashboard-vendor" / "clonehorse" / "index.html",
        REPO_ROOT / "subprojects" / "prediction" / "dashboard-vendor" / "firehorse" / "firehorse-dashboard.html",
        REPO_ROOT / "subprojects" / "prediction" / "dashboard-vendor" / "askelira-trader" / "static" / "index.html",
    ]
    for path in expected:
        assert path.exists(), f"missing expected dashboard artifact: {path}"


def test_dashboard_launcher_smoke_help() -> None:
    candidates = [
        REPO_ROOT / "subprojects" / "prediction" / "scripts" / "prediction-dashboard.cjs",
        REPO_ROOT / "scripts" / "swarm-dashboard.cjs",
        REPO_ROOT / "subprojects" / "prediction" / "scripts" / "prediction-dashboard-ui-adapter.cjs",
    ]

    assert candidates[0].exists(), f"missing expected dashboard launcher: {candidates[0]}"

    for path in candidates:
        if not path.exists():
            continue

        result = subprocess.run(
            ["node", str(path), "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        combined_output = f"{result.stdout}\n{result.stderr}".lower()
        assert result.returncode == 0, f"{path} --help failed: {combined_output}"
        assert "help" in combined_output or "usage" in combined_output, f"{path} --help did not print usage"


def test_swarm_dashboard_compat_endpoints_smoke() -> None:
    script = REPO_ROOT / "scripts" / "swarm-dashboard.cjs"
    legacy_root = REPO_ROOT / "tmp" / "test-swarm-dashboard-legacy"
    if legacy_root.exists():
        subprocess.run(["rm", "-rf", str(legacy_root)], check=False)

    with launch_node_server(["node", str(script), "--port", "5061", "--legacy-data-root", str(legacy_root)]):
        project = wait_json("http://127.0.0.1:5061/api/graph/project/swarm-demo-project")
        history = wait_json("http://127.0.0.1:5061/api/simulation/history")
        root_html = urlopen("http://127.0.0.1:5061/dashboard/swarm-ui/", timeout=2).read().decode("utf-8")

    assert project["success"] is True
    assert project["data"]["project_id"] == "swarm-demo-project"
    assert history["success"] is True
    assert len(history["data"]) >= 1
    assert "<!doctype html" in root_html.lower() or "swarm dashboard" in root_html.lower()
    assert legacy_root.joinpath("state.json").exists()


def test_prediction_dashboard_adapter_compat_endpoints_smoke() -> None:
    script = REPO_ROOT / "subprojects" / "prediction" / "scripts" / "prediction-dashboard-ui-adapter.cjs"
    state_file = REPO_ROOT / "tmp" / "test-prediction-dashboard-ui-adapter-state.json"
    if state_file.exists():
        state_file.unlink()

    with launch_node_server(["node", str(script), "--port", "5003", "--state-file", str(state_file)]):
        settings = wait_json("http://127.0.0.1:5003/api/polymarket/settings")
        knowledge = wait_json("http://127.0.0.1:5003/api/polymarket/knowledge/stats")
        legacy_project = wait_json("http://127.0.0.1:5003/api/graph/project/prediction-demo-project")
        root_html = urlopen("http://127.0.0.1:5003/", timeout=2).read().decode("utf-8")

    assert settings["success"] is True
    assert settings["data"]["pipeline_preset"] == "balanced"
    assert knowledge["success"] is True
    assert knowledge["data"]["total_entries"] >= 1
    assert legacy_project["success"] is True
    assert legacy_project["data"]["project_id"] == "prediction-demo-project"
    assert "<!doctype html" in root_html.lower() or "prediction-dashboard-ui-adapter" in root_html.lower()
    assert state_file.exists()
