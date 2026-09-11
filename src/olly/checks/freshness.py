from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from olly.config import ResolvedTableSettings, Settings
from olly.models import Finding, TableInfo
from olly.state import BaseStateStore

if TYPE_CHECKING:
    from olly.adapter import Adapter

logger = logging.getLogger(__name__)


def check_freshness(
    backend: Adapter,
    tables: list[TableInfo],
    settings: Settings,
    overrides: dict[tuple[str, str], ResolvedTableSettings],
    state_db: BaseStateStore,
    connection_name: str = "",
) -> list[Finding]:
    """Check tables for stale data, preferring catalog metadata over scans.

    Each table resolves to one of three strategies via ``freshness_method``:

    ``metadata``
        Compare the warehouse's own last-modified time (BigQuery
        ``storage_last_modified_time``, Snowflake ``LAST_ALTERED``) against
        the threshold. Costs a small fixed number of queries for the whole
        run regardless of table count, and never scans table data.
    ``column``
        Compare ``MAX(freshness_column)`` against the threshold. Reflects
        business event time rather than write time, at the cost of a scan
        per table.
    ``auto`` (default)
        Use ``column`` when a ``freshness_column`` is explicitly configured
        for the table -- that is a deliberate statement about which
        timestamp matters -- otherwise ``metadata``.

    When the chosen strategy is unavailable (no metadata support on the
    adapter, or no ``freshness_column`` configured), the table falls back to
    the row-count staleness proxy.

    Args:
        backend: Warehouse adapter for metadata and timestamp queries.
        tables: Current table schemas to evaluate.
        settings: Global settings (thresholds, history depth).
        overrides: Per-table setting overrides keyed by
            ``(schema_name, table_name)``.
        state_db: State database for historical volume lookups.
        connection_name: Connection these tables belong to.

    Returns:
        A list of findings for tables detected as stale.
    """
    findings: list[Finding] = []
    logger.debug("Running freshness check for %d tables", len(tables))

    now = datetime.now(timezone.utc)

    candidates = [ti for ti in tables if ti.table_type != "VIEW"]
    strategies = {
        (ti.schema_name, ti.table_name): _resolve_strategy(
            backend, settings, overrides.get((ti.schema_name, ti.table_name))
        )
        for ti in candidates
    }

    last_modified = _fetch_last_modified(
        backend, [ti for ti in candidates if strategies[_key(ti)] == "metadata"]
    )

    for ti in candidates:
        key = _key(ti)
        override = overrides.get(key)
        threshold_hours = (
            override.freshness_threshold_hours
            if override is not None
            else settings.freshness_threshold_hours
        )

        strategy = strategies[key]
        finding: Finding | None = None
        if strategy == "metadata":
            modified_at = last_modified.get(key)
            if modified_at is not None:
                finding = _stale_finding(
                    ti, modified_at, threshold_hours, now,
                    method="metadata", source="catalog_last_modified",
                )
            else:
                logger.debug(
                    "No catalog last-modified for %s.%s; using staleness proxy",
                    ti.schema_name, ti.table_name,
                )
                finding = _check_staleness_proxy(
                    ti, state_db, settings, connection_name
                )
        elif strategy == "column":
            column = override.freshness_column if override else None
            assert column is not None  # guaranteed by _resolve_strategy
            finding = _check_timestamp_freshness(
                backend, ti, column, threshold_hours, now
            )
        else:
            finding = _check_staleness_proxy(ti, state_db, settings, connection_name)

        if finding:
            findings.append(finding)

    return findings


def _key(table: TableInfo) -> tuple[str, str]:
    """Return the ``(schema, table)`` key used across the lookup maps."""
    return (table.schema_name, table.table_name)


def _resolve_strategy(
    backend: Adapter,
    settings: Settings,
    override: ResolvedTableSettings | None,
) -> str:
    """Pick ``metadata``, ``column``, or ``proxy`` for a single table."""
    method = override.freshness_method if override else settings.freshness_method
    has_column = bool(override and override.freshness_column)
    supports_metadata = getattr(backend, "SUPPORTS_METADATA_FRESHNESS", False)

    if method == "column":
        return "column" if has_column else "proxy"
    if method == "metadata":
        return "metadata" if supports_metadata else "proxy"
    # auto: an explicitly configured column wins, else metadata, else proxy.
    if has_column:
        return "column"
    return "metadata" if supports_metadata else "proxy"


def _fetch_last_modified(
    backend: Adapter, tables: list[TableInfo]
) -> dict[tuple[str, str], datetime]:
    """Batch-fetch catalog last-modified times, tolerating adapter failures."""
    if not tables:
        return {}
    try:
        return backend.fetch_last_modified(tables)
    except Exception:
        logger.exception(
            "Failed to fetch catalog last-modified times; "
            "falling back to the staleness proxy"
        )
        return {}


def _stale_finding(
    table: TableInfo,
    modified_at: datetime,
    threshold_hours: float,
    now: datetime,
    *,
    method: str,
    source: str,
    extra_details: dict | None = None,
) -> Finding | None:
    """Build a staleness finding when *modified_at* exceeds the threshold."""
    if modified_at.tzinfo is None:
        modified_at = modified_at.replace(tzinfo=timezone.utc)

    age_hours = (now - modified_at).total_seconds() / 3600
    if age_hours <= threshold_hours:
        return None

    details = {
        "method": method,
        "source": source,
        "last_modified_at": modified_at.isoformat(),
        "age_hours": round(age_hours, 1),
        "threshold_hours": threshold_hours,
    }
    details.update(extra_details or {})
    return Finding(
        check_type="freshness",
        severity="warning" if age_hours < threshold_hours * 2 else "error",
        schema_name=table.schema_name,
        table_name=table.table_name,
        description=(
            f"Stale data: {table.schema_name}.{table.table_name} "
            f"— last update {age_hours:.1f}h ago (threshold: {threshold_hours}h)"
        ),
        details=details,
    )


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
            details={
                "method": "column",
                "column": column,
                "reason": "null_or_unreadable",
            },
        )

    return _stale_finding(
        table, max_ts, threshold_hours, now,
        method="column",
        source=f"MAX({column})",
        extra_details={"column": column, "max_timestamp": _isoformat(max_ts)},
    )


def _isoformat(value: datetime) -> str:
    """Return an ISO-8601 string, assuming UTC for naive datetimes."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _check_staleness_proxy(
    table: TableInfo,
    state_db: BaseStateStore,
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
                "method": "proxy",
                "unchanged_snapshots": unchanged,
                "reason": "row_count_unchanged",
            },
        )
    return None
