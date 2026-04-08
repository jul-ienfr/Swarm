from __future__ import annotations

import importlib


def test_harness_optimizer_module_exports_core_types() -> None:
    module = importlib.import_module("swarm_core.harness_optimizer")

    assert hasattr(module, "HarnessOptimizer")
    assert hasattr(module, "HarnessSnapshot")
    assert hasattr(module, "HarnessMemoryStore")
    assert hasattr(module, "OptimizationMode")


def test_harness_optimizer_defaults_to_suggest_only() -> None:
    module = importlib.import_module("swarm_core.harness_optimizer")
    optimizer = module.HarnessOptimizer()

    assert optimizer.suggest_only is True
    assert optimizer.stagnation_limit >= 1
    assert hasattr(optimizer, "run_optimization_round")
