from __future__ import annotations

import math


def _finite_probability(value: float) -> float:
    probability = float(value)
    if not math.isfinite(probability):
        raise ValueError("probability must be finite")
    return probability


def clamp_probability(value: float) -> float:
    probability = _finite_probability(value)
    return max(0.0, min(1.0, probability))


def log_loss(probability_yes: float, outcome_yes: bool) -> float:
    probability_yes = _finite_probability(probability_yes)
    probability_yes = max(1e-9, min(1.0 - 1e-9, probability_yes))
    return -math.log(probability_yes if outcome_yes else 1.0 - probability_yes)


def ece_bucket(probability: float, bins: int = 10) -> str:
    bins = max(1, int(bins))
    clamped = clamp_probability(probability)
    index = min(bins - 1, int(clamped * bins))
    lower = index / bins
    upper = (index + 1) / bins

    reduced = bins
    factor_two = 0
    factor_five = 0
    while reduced % 2 == 0:
        reduced //= 2
        factor_two += 1
    while reduced % 5 == 0:
        reduced //= 5
        factor_five += 1
    precision = max(factor_two, factor_five) if reduced == 1 else 6

    return f"{lower:.{precision}f}-{upper:.{precision}f}"
