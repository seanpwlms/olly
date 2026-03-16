"""dbt per-model execution time anomaly detection using EWMA."""

from __future__ import annotations

import logging

from olly.checks.stats import compute_ewma
from olly.models import DbtFinding
from olly.state import BaseStateStore

logger = logging.getLogger(__name__)


def check_dbt_performance(
    dbt_findings: list[DbtFinding],
    state_db: BaseStateStore,
    threshold: float = 3.0,
    min_history: int = 5,
) -> list[DbtFinding]:
    """Detect execution time anomalies across dbt nodes using EWMA.

    For each non-skipped node, fetches historical execution times and computes
    an EWMA deviation score. If the score exceeds the threshold, a warning
    finding is emitted.

    Args:
        dbt_findings: Current run's dbt findings (used for node list).
        state_db: State store for historical timing data.
        threshold: EWMA deviation score threshold.
        min_history: Minimum number of historical runs required.

    Returns:
        List of performance anomaly findings.
    """
    perf_findings: list[DbtFinding] = []

    for f in dbt_findings:
        if f.status == "skipped":
            continue

        history = state_db.get_dbt_node_execution_history(f.unique_id, depth=30)
        if len(history) < min_history:
            continue

        # Current run's timing is already stored, so it's history[0].
        # Compare against the rest.
        current = history[0]
        baseline = history[1:]

        if len(baseline) < min_history:
            continue

        score = compute_ewma(current, baseline)
        if score is not None and abs(score) > threshold:
            direction = "slower" if score > 0 else "faster"
            perf_findings.append(
                DbtFinding(
                    resource_type=f.resource_type,
                    severity="warning",
                    unique_id=f.unique_id,
                    status="performance_anomaly",
                    execution_time=f.execution_time,
                    description=(
                        f"Execution time anomaly ({direction}): "
                        f"{f.unique_id} ({f.execution_time:.1f}s, "
                        f"score: {score:+.2f})"
                    ),
                    details={
                        "unique_id": f.unique_id,
                        "resource_type": f.resource_type,
                        "status": "performance_anomaly",
                        "execution_time": f.execution_time,
                        "score": round(score, 2),
                        "threshold": threshold,
                        "history_depth": len(baseline),
                        "performance_anomaly": True,
                    },
                )
            )

    logger.info("dbt performance check: %d anomalies detected", len(perf_findings))
    return perf_findings
