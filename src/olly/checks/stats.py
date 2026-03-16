"""Shared statistical functions for anomaly detection."""

from __future__ import annotations

import math
import statistics


def compute_zscore(value: float, history: list[float]) -> float | None:
    """Compute the z-score of a value relative to a history of observations.

    Args:
        value: The current observation to score.
        history: Previous observations (must have at least 2 entries).

    Returns:
        The z-score as a float, or ``None`` if history is too short.
        Returns ``inf`` / ``-inf`` when standard deviation is zero but the
        value differs from the mean.
    """
    if len(history) < 2:
        return None
    mean = statistics.mean(history)
    stdev = statistics.stdev(history)
    if stdev == 0:
        if value == mean:
            return None
        # Use a large finite value so the result is JSON-serializable.
        return 1e6 if value > mean else -1e6
    return (value - mean) / stdev


def compute_ewma(value: float, history: list[float], alpha: float = 0.3) -> float | None:
    """Compute an EWMA-based deviation score for a value against history.

    Uses Exponentially Weighted Moving Average to compute a mean and variance
    over the history, weighting recent observations more heavily. Returns a
    z-score-like deviation measure: ``(value - ewma_mean) / sqrt(ewma_variance)``.

    Args:
        value: The current observation to score.
        history: Previous observations (newest first from storage; reversed
            internally for chronological processing).
        alpha: Decay factor (0 < alpha <= 1). Higher values weight recent
            observations more. Default 0.3.

    Returns:
        The deviation score as a float, or ``None`` if history is too short
        or variance is zero and value matches the mean.
    """
    if len(history) < 2:
        return None

    # History comes newest-first from state_db; reverse to process chronologically
    chronological = list(reversed(history))

    ewma_mean = float(chronological[0])
    ewma_var = 0.0

    for x in chronological[1:]:
        diff = x - ewma_mean
        ewma_mean = alpha * x + (1 - alpha) * ewma_mean
        ewma_var = (1 - alpha) * (ewma_var + alpha * diff * diff)

    if ewma_var <= 0:
        if value == ewma_mean:
            return None
        return 1e6 if value > ewma_mean else -1e6

    return (value - ewma_mean) / math.sqrt(ewma_var)
