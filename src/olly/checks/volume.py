from __future__ import annotations

import logging
import math
import statistics

from olly.config import Settings
from olly.models import Finding, VolumeRecord
from olly.state import BaseStateStore

logger = logging.getLogger(__name__)


def check_volume(
    current: list[VolumeRecord],
    state_db: BaseStateStore,
    settings: Settings,
    thresholds: dict[tuple[str, str], float] | None = None,
    methods: dict[tuple[str, str], str] | None = None,
    connection_name: str = "",
) -> list[Finding]:
    """Detect row-count anomalies using z-score or EWMA analysis against historical data.

    Args:
        current: Current row-count records for each table.
        state_db: State database providing historical volume data.
        settings: Global settings (z-score threshold, history depth, etc.).
        thresholds: Optional per-table z-score threshold overrides, keyed by
            ``(schema_name, table_name)``.
        methods: Optional per-table volume method overrides, keyed by
            ``(schema_name, table_name)``. Values are ``"ewma"`` or ``"zscore"``.

    Returns:
        A list of findings for tables whose row counts are anomalous.
    """
    findings: list[Finding] = []
    thresholds = thresholds or {}
    methods = methods or {}
    logger.debug("Running volume check for %d tables", len(current))

    for vol in current:
        key = (vol.schema_name, vol.table_name)
        threshold = thresholds.get(key, settings.volume_zscore_threshold)
        method = methods.get(key, settings.volume_method)
        min_history = settings.min_history_for_anomaly

        history = state_db.get_volume_history(
            vol.schema_name, vol.table_name, settings.history_depth,
            connection_name=connection_name,
        )
        # Exclude the latest snapshot from history since current is the latest snapshot
        # We want to compare current against the historical baseline, not including itself
        if len(history) > 0 and history[0] == vol.row_count:
            baseline_history = history[1:]
        else:
            baseline_history = history

        if len(baseline_history) < min_history:
            continue

        if method == "ewma":
            score = _compute_ewma(vol.row_count, baseline_history)
        else:
            score = _compute_zscore(vol.row_count, baseline_history)

        if score is not None and abs(score) > threshold:
            direction = "increase" if score > 0 else "decrease"
            findings.append(
                Finding(
                    check_type="volume",
                    severity="warning" if abs(score) < threshold * 2 else "error",
                    schema_name=vol.schema_name,
                    table_name=vol.table_name,
                    description=(
                        f"Row count anomaly ({direction}): "
                        f"{vol.schema_name}.{vol.table_name} "
                        f"({vol.row_count:,} rows, z-score: {score:+.2f})"
                    ),
                    details={
                        "current_count": vol.row_count,
                        "z_score": round(score, 2),
                        "threshold": threshold,
                        "method": method,
                        "history_mean": round(statistics.mean(baseline_history), 2),
                        "history_stdev": round(statistics.stdev(baseline_history), 2),
                        "history_depth": len(baseline_history),
                    },
                )
            )

    return findings


def _compute_zscore(value: int, history: list[int]) -> float | None:
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


def _compute_ewma(value: int, history: list[int], alpha: float = 0.3) -> float | None:
    """Compute an EWMA-based deviation score for a value against history.

    Uses Exponentially Weighted Moving Average to compute a mean and variance
    over the history, weighting recent observations more heavily. Returns a
    z-score-like deviation measure: ``(value - ewma_mean) / sqrt(ewma_variance)``.

    Args:
        value: The current observation to score.
        history: Previous observations (oldest first internally; the list is
            reversed from newest-first storage order).
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
