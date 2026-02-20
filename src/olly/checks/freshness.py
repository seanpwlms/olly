from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from olly.config import ResolvedTableSettings, Settings
from olly.models import Finding, TableInfo
from olly.state import StateStore

if TYPE_CHECKING:
    from olly.adapter import Adapter

logger = logging.getLogger(__name__)


def check_freshness(
    backend: Adapter,
    tables: list[TableInfo],
    settings: Settings,
    overrides: dict[tuple[str, str], ResolvedTableSettings],
    state_db: StateStore,
    connection_name: str = "",
) -> list[Finding]:
    """Check tables for stale data using timestamps or row-count heuristics.

    For each non-view table, uses a timestamp-based freshness check if a
    ``freshness_column`` override is configured, otherwise falls back to a
    staleness proxy based on consecutive unchanged row counts.

    Args:
        backend: Warehouse adapter for querying max timestamps.
        tables: Current table schemas to evaluate.
        settings: Global settings (thresholds, history depth).
        overrides: Per-table setting overrides keyed by
            ``(schema_name, table_name)``.
        state_db: State database for historical volume lookups.

    Returns:
        A list of findings for tables detected as stale.
    """
    findings: list[Finding] = []
    logger.debug("Running freshness check for %d tables", len(tables))

    now = datetime.now(timezone.utc)

    for ti in tables:
        if ti.table_type == "VIEW":
            continue

        key = (ti.schema_name, ti.table_name)
        override = overrides.get(key)

        threshold_hours = (
            override.freshness_threshold_hours
            if override is not None
            else settings.freshness_threshold_hours
        )

        # If a freshness_column is configured, use timestamp-based check
        freshness_col = override.freshness_column if override else None
        if freshness_col:
            finding = _check_timestamp_freshness(
                backend, ti, freshness_col, threshold_hours, now
            )
            if finding:
                findings.append(finding)
        else:
            # Staleness proxy: row count unchanged across recent snapshots
            finding = _check_staleness_proxy(ti, state_db, settings, connection_name)
            if finding:
                findings.append(finding)

    return findings


def _check_timestamp_freshness(
    backend: Adapter,
    table: TableInfo,
    column: str,
    threshold_hours: float,
    now: datetime,
) -> Finding | None:
    """Check freshness by comparing a column's MAX timestamp against a threshold."""
    max_ts = backend.fetch_max_timestamp(table.schema_name, table.table_name, column)
    if max_ts is None:
        return Finding(
            check_type="freshness",
            severity="warning",
            schema_name=table.schema_name,
            table_name=table.table_name,
            description=(
                f"Freshness check failed: {table.schema_name}.{table.table_name} "
                f"— could not read MAX({column})"
            ),
            details={"column": column, "reason": "null_or_unreadable"},
        )

    if max_ts.tzinfo is None:
        max_ts = max_ts.replace(tzinfo=timezone.utc)

    age_hours = (now - max_ts).total_seconds() / 3600
    if age_hours > threshold_hours:
        return Finding(
            check_type="freshness",
            severity="warning" if age_hours < threshold_hours * 2 else "error",
            schema_name=table.schema_name,
            table_name=table.table_name,
            description=(
                f"Stale data: {table.schema_name}.{table.table_name} "
                f"— last update {age_hours:.1f}h ago (threshold: {threshold_hours}h)"
            ),
            details={
                "column": column,
                "max_timestamp": max_ts.isoformat(),
                "age_hours": round(age_hours, 1),
                "threshold_hours": threshold_hours,
            },
        )
    return None


def _check_staleness_proxy(
    table: TableInfo,
    state_db: StateStore,
    settings: Settings,
    connection_name: str = "",
) -> Finding | None:
    """Detect staleness when row count is unchanged across recent snapshots."""
    unchanged = state_db.get_recent_volume_unchanged_count(
        table.schema_name, table.table_name, settings.min_history_for_anomaly,
        connection_name=connection_name,
    )
    if unchanged >= settings.min_history_for_anomaly:
        return Finding(
            check_type="freshness",
            severity="warning",
            schema_name=table.schema_name,
            table_name=table.table_name,
            description=(
                f"Possible stale data: {table.schema_name}.{table.table_name} "
                f"— row count unchanged for {unchanged} consecutive snapshots"
            ),
            details={
                "unchanged_snapshots": unchanged,
                "reason": "row_count_unchanged",
            },
        )
    return None
