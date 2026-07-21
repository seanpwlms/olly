from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from olly.models import Finding, SchemaUsageSummary, TableUsageStatus

if TYPE_CHECKING:
    from olly.adapter import Adapter
    from olly.config import UsageConfig

logger = logging.getLogger(__name__)

# Max table names embedded in a schema-level finding's details
ROLLUP_TABLE_LIST_CAP = 20


def classify_table_usage(
    adapter: Adapter,
    schemas: list[str],
    usage_config: UsageConfig,
    all_tables: list[tuple[str, str]] | None = None,
) -> list[TableUsageStatus]:
    """Fetch query history and classify each table as active, stale, or unused.

    Uses warehouse query history (e.g. BigQuery INFORMATION_SCHEMA.JOBS_BY_PROJECT)
    to determine each table's last access. Tables that don't appear in query
    history at all are classified as unused.

    Args:
        adapter: Warehouse adapter.
        schemas: Schema names to check usage for.
        usage_config: Usage check configuration.
        all_tables: Optional list of all (schema, table) pairs to cross-reference.
            Tables absent from query history are classified as unused.

    Returns:
        One ``TableUsageStatus`` per table, sorted by (schema, table).
    """
    if not getattr(adapter, "SUPPORTS_USAGE_HISTORY", False):
        logger.info(
            "Adapter does not report query history; skipping usage check"
        )
        return []

    try:
        usage_records = adapter.fetch_table_usage(
            schemas=schemas,
            lookback_days=usage_config.lookback_days,
            region=usage_config.bigquery_region,
        )
    except Exception:
        logger.exception("Failed to fetch table usage")
        return []

    now = datetime.now(timezone.utc)
    threshold_days = usage_config.unused_threshold_days

    statuses: dict[tuple[str, str], TableUsageStatus] = {}
    for record in usage_records:
        key = (record.schema_name, record.table_name)
        last_queried = record.last_queried_at
        if last_queried is None:
            statuses[key] = TableUsageStatus(
                schema_name=record.schema_name,
                table_name=record.table_name,
                status="unused",
                last_queried_at=None,
                days_unused=None,
            )
            continue

        if last_queried.tzinfo is None:
            last_queried = last_queried.replace(tzinfo=timezone.utc)
        days_unused = (now - last_queried).total_seconds() / 86400
        statuses[key] = TableUsageStatus(
            schema_name=record.schema_name,
            table_name=record.table_name,
            status="stale" if days_unused > threshold_days else "active",
            last_queried_at=last_queried,
            days_unused=days_unused,
        )

    # Tables completely absent from query history are unused
    for schema_name, table_name in all_tables or []:
        key = (schema_name, table_name)
        if key not in statuses:
            statuses[key] = TableUsageStatus(
                schema_name=schema_name,
                table_name=table_name,
                status="unused",
                last_queried_at=None,
                days_unused=None,
            )

    return [statuses[key] for key in sorted(statuses)]


def summarize_schema_usage(
    statuses: list[TableUsageStatus],
) -> list[SchemaUsageSummary]:
    """Aggregate per-table usage statuses into per-schema summaries.

    Returns:
        One ``SchemaUsageSummary`` per schema, sorted most-inactive first.
    """
    by_schema: dict[str, list[TableUsageStatus]] = {}
    for status in statuses:
        by_schema.setdefault(status.schema_name, []).append(status)

    summaries = []
    for schema_name, tables in by_schema.items():
        counts = {"active": 0, "stale": 0, "unused": 0}
        for t in tables:
            counts[t.status] += 1
        total = len(tables)
        inactive = counts["stale"] + counts["unused"]
        queried = [
            t.last_queried_at for t in tables if t.last_queried_at is not None
        ]
        summaries.append(
            SchemaUsageSummary(
                schema_name=schema_name,
                total_tables=total,
                active_count=counts["active"],
                stale_count=counts["stale"],
                unused_count=counts["unused"],
                inactive_pct=100.0 * inactive / total,
                last_activity_at=max(queried) if queried else None,
                fully_inactive=counts["active"] == 0,
            )
        )

    return sorted(summaries, key=lambda s: (-s.inactive_pct, s.schema_name))


def _table_finding(
    status: TableUsageStatus, usage_config: UsageConfig
) -> Finding:
    """Build the per-table unused/stale finding."""
    threshold_days = usage_config.unused_threshold_days
    if status.last_queried_at is None:
        description = (
            f"Unused table: {status.schema_name}.{status.table_name}"
            f" — no queries in past {usage_config.lookback_days} days"
        )
        details = {
            "last_queried_at": None,
            "lookback_days": usage_config.lookback_days,
            "threshold_days": threshold_days,
        }
    else:
        description = (
            f"Stale table: {status.schema_name}.{status.table_name}"
            f" — last queried {status.days_unused:.0f} days ago"
            f" (threshold: {threshold_days} days)"
        )
        details = {
            "last_queried_at": status.last_queried_at.isoformat(),
            "days_unused": round(status.days_unused or 0.0, 1),
            "threshold_days": threshold_days,
            "lookback_days": usage_config.lookback_days,
        }
    return Finding(
        check_type="usage",
        severity=usage_config.severity,
        schema_name=status.schema_name,
        table_name=status.table_name,
        description=description,
        details=details,
    )


def _schema_finding(
    summary: SchemaUsageSummary,
    inactive_tables: list[str],
    usage_config: UsageConfig,
) -> Finding:
    """Build the schema-level rollup finding.

    "Unused" here means no queries in the warehouse's *visible* query
    history (e.g. project-scoped on BigQuery), so the description hedges
    accordingly rather than claiming the schema was never used.
    """
    threshold_days = usage_config.unused_threshold_days
    if summary.fully_inactive:
        description = (
            f"Unused schema: {summary.schema_name}"
            f" — all {summary.total_tables} table(s) have had no queries"
            f" in visible history for over {threshold_days} days"
        )
    else:
        description = (
            f"Mostly unused schema: {summary.schema_name}"
            f" — {summary.inactive_pct:.0f}% of {summary.total_tables}"
            f" table(s) have had no queries in visible history"
            f" for over {threshold_days} days"
        )
    return Finding(
        check_type="usage",
        severity=usage_config.severity,
        schema_name=summary.schema_name,
        table_name="*",
        description=description,
        details={
            "scope": "schema",
            "table_count": summary.total_tables,
            "unused_count": summary.unused_count,
            "stale_count": summary.stale_count,
            "inactive_pct": round(summary.inactive_pct, 1),
            "last_activity_at": (
                summary.last_activity_at.isoformat()
                if summary.last_activity_at
                else None
            ),
            "tables": inactive_tables[:ROLLUP_TABLE_LIST_CAP],
            "tables_truncated": len(inactive_tables) > ROLLUP_TABLE_LIST_CAP,
            "lookback_days": usage_config.lookback_days,
            "threshold_days": threshold_days,
        },
    )


def build_usage_findings(
    statuses: list[TableUsageStatus], usage_config: UsageConfig
) -> list[Finding]:
    """Turn table usage statuses into findings, rolling up dead schemas.

    When ``usage_config.rollup_schemas`` is enabled, a schema whose
    inactive percentage meets ``schema_unused_threshold_pct`` produces a
    single schema-level finding (``table_name="*"``). If the schema is
    fully inactive its per-table findings are suppressed; partially
    inactive schemas keep them alongside the rollup.
    """
    findings: list[Finding] = []

    rolled_up: dict[str, SchemaUsageSummary] = {}
    if usage_config.rollup_schemas:
        for summary in summarize_schema_usage(statuses):
            inactive = summary.stale_count + summary.unused_count
            if (
                inactive > 0
                and summary.inactive_pct
                >= usage_config.schema_unused_threshold_pct
            ):
                rolled_up[summary.schema_name] = summary

    for schema_name, summary in rolled_up.items():
        inactive_tables = [
            s.table_name
            for s in statuses
            if s.schema_name == schema_name and s.status != "active"
        ]
        findings.append(_schema_finding(summary, inactive_tables, usage_config))

    for status in statuses:
        if status.status == "active":
            continue
        rollup = rolled_up.get(status.schema_name)
        if rollup is not None and rollup.fully_inactive:
            continue  # suppressed by the schema-level finding
        findings.append(_table_finding(status, usage_config))

    return findings


def check_usage(
    adapter: Adapter,
    schemas: list[str],
    usage_config: UsageConfig,
    all_tables: list[tuple[str, str]] | None = None,
) -> list[Finding]:
    """Identify unused/stale tables and fully-unused schemas.

    Args:
        adapter: Warehouse adapter.
        schemas: Schema names to check usage for.
        usage_config: Usage check configuration.
        all_tables: Optional list of all (schema, table) pairs to cross-reference.
            Tables absent from query history are flagged as unused.

    Returns:
        Findings for unused or stale tables, plus schema-level rollup
        findings when ``usage_config.rollup_schemas`` is enabled.
    """
    statuses = classify_table_usage(adapter, schemas, usage_config, all_tables)
    return build_usage_findings(statuses, usage_config)
