from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from olly.models import CostRecord, Finding

if TYPE_CHECKING:
    from olly.adapter import Adapter
    from olly.config import CostConfig
    from olly.state import StateStore

logger = logging.getLogger(__name__)


def check_cost(
    adapter: Adapter,
    schemas: list[str],
    cost_config: CostConfig,
    state_db: StateStore,
    connection_name: str = "",
) -> tuple[list[CostRecord], list[Finding]]:
    """Fetch query costs and detect cost anomalies.

    Args:
        adapter: Warehouse adapter.
        schemas: Schema names to check costs for.
        cost_config: Cost check configuration.
        state_db: State database for historical cost data.

    Returns:
        Tuple of (cost records, findings). Cost records are always returned
        for storage; findings are generated only for anomalies.
    """
    try:
        records = adapter.fetch_query_costs(
            schemas=schemas,
            lookback_days=cost_config.lookback_days,
            region=cost_config.bigquery_region,
            price_per_tb_usd=cost_config.price_per_tb_usd,
        )
    except Exception:
        logger.exception("Failed to fetch query costs")
        return [], []

    findings = _detect_cost_anomalies(
        records, state_db, cost_config.spike_threshold, connection_name
    )

    return records, findings


def _detect_cost_anomalies(
    current_records: list[CostRecord],
    state_db: StateStore,
    spike_threshold: float,
    connection_name: str = "",
) -> list[Finding]:
    """Compare current total cost against historical average using z-score."""
    current_total = sum(r.estimated_cost_usd for r in current_records)
    if current_total == 0:
        return []

    history = state_db.get_cost_history(depth=30, connection_name=connection_name)
    if len(history) < 3:
        return []

    historical_costs = [cost for _, cost in history]
    mean = sum(historical_costs) / len(historical_costs)
    if mean == 0:
        return []

    variance = sum((c - mean) ** 2 for c in historical_costs) / len(historical_costs)
    stddev = math.sqrt(variance)

    if stddev == 0:
        return []

    z_score = (current_total - mean) / stddev

    if z_score > spike_threshold:
        return [
            Finding(
                check_type="cost",
                severity="warning",
                schema_name="*",
                table_name="*",
                description=(
                    f"Cost spike detected: ${current_total:.2f} "
                    f"(z-score: {z_score:.1f}, "
                    f"mean: ${mean:.2f}, stddev: ${stddev:.2f})"
                ),
                details={
                    "current_cost_usd": round(current_total, 2),
                    "mean_cost_usd": round(mean, 2),
                    "stddev_cost_usd": round(stddev, 2),
                    "z_score": round(z_score, 1),
                    "threshold": spike_threshold,
                },
            )
        ]

    return []


def summarize_costs(records: list[CostRecord]) -> dict:
    """Produce a cost summary suitable for display or JSON output.

    Args:
        records: Cost records for the current period.

    Returns:
        Dictionary with total_cost_usd, top_tables, and top_users.
    """
    total_cost = sum(r.estimated_cost_usd for r in records)

    table_costs: dict[tuple[str, str], float] = {}
    user_costs: dict[str, float] = {}
    for r in records:
        key = (r.schema_name, r.table_name)
        table_costs[key] = table_costs.get(key, 0.0) + r.estimated_cost_usd
        user_costs[r.user_email] = (
            user_costs.get(r.user_email, 0.0) + r.estimated_cost_usd
        )

    top_tables = sorted(table_costs.items(), key=lambda x: x[1], reverse=True)[:10]
    top_users = sorted(user_costs.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "total_cost_usd": round(total_cost, 2),
        "top_tables": [
            {"schema": s, "table": t, "cost_usd": round(c, 2)}
            for (s, t), c in top_tables
        ],
        "top_users": [{"user": u, "cost_usd": round(c, 2)} for u, c in top_users],
    }
