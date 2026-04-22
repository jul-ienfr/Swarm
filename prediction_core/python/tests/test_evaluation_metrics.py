from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from prediction_core.evaluation import clamp_probability, ece_bucket, log_loss


def test_clamp_probability_bounds_values_to_zero_one() -> None:
    assert clamp_probability(-0.2) == 0.0
    assert clamp_probability(0.42) == 0.42
    assert clamp_probability(1.3) == 1.0


def test_log_loss_uses_clamped_probability_and_outcome_side() -> None:
    assert log_loss(0.0, True) == pytest.approx(-math.log(1e-9))
    assert log_loss(1.0, False) == pytest.approx(-math.log(1e-9))
    assert log_loss(0.75, True) == pytest.approx(-math.log(0.75))


def test_ece_bucket_formats_probability_bins() -> None:
    assert ece_bucket(0.0) == "0.0-0.1"
    assert ece_bucket(0.42) == "0.4-0.5"
    assert ece_bucket(1.0) == "0.9-1.0"
    assert ece_bucket(0.42, bins=4) == "0.25-0.50"
    assert ece_bucket(0.42, bins=20) == "0.40-0.45"
    assert ece_bucket(0.42, bins=3) == "0.333333-0.666667"


def test_probability_helpers_reject_non_finite_inputs() -> None:
    non_finite_values = [float("nan"), float("inf"), float("-inf")]

    for value in non_finite_values:
        with pytest.raises(ValueError, match="probability must be finite"):
            clamp_probability(value)
        with pytest.raises(ValueError, match="probability must be finite"):
            log_loss(value, True)
        with pytest.raises(ValueError, match="probability must be finite"):
            ece_bucket(value)
