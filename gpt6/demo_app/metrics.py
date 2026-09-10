"""Small, deterministic example target for evidence-backed refactoring."""
from math import isfinite


def success_rate(outcomes: list[bool]) -> float | None:
    """Unknown (None) for no observations; booleans only."""
    if any(type(value) is not bool for value in outcomes):
        raise ValueError("Outcomes must be verified booleans")
    if not outcomes:
        return None
    return sum(outcomes) / len(outcomes)


def weighted_cost(costs: list[float], weights: list[float]) -> float:
    if len(costs) != len(weights):
        raise ValueError("Equal lengths are required")
    for value in costs + weights:
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value) or value < 0:
            raise ValueError("Finite nonnegative numeric values are required")
    return sum(cost * weight for cost, weight in zip(costs, weights))
