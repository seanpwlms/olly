from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from olly.config import load_config
from olly.models import ColumnInfo, DbtFinding, Finding, TableInfo
from olly.results import get_default_findings_path
from olly.state import BaseStateStore


def get_all_connections() -> list[str]:
    """Return list of all configured connection names."""
    config = load_config()
    return list(config.connections.keys())


@dataclass
class VolumeStats:
    current: int | None
    previous: int | None
    delta: int | None
    delta_pct: float | None
    minimum: int | None
    maximum: int | None
    average: float | None
    snapshot_count: int


@dataclass
class TableHistory:
    first_seen: str | None
    snapshot_count: int


@dataclass
class SchemaDiff:
    added: list[ColumnInfo]
    removed: list[ColumnInfo]
    type_changes: list[tuple[str, str, str]]  # (column, old_type, new_type)
    nullable_changes: list[tuple[str, bool, bool]]  # (column, old, new)


@dataclass
class FindingsStats:
    total_count: int
    error_count: int
    warning_count: int
    by_check_type: dict[str, tuple[int, int]]  # {check_type: (errors, warnings)}
    by_connection: dict[str, tuple[int, int]]  # {connection: (errors, warnings)}


@dataclass
class SnapshotInfo:
    snapshot_id: int
    created_at: str
    connection_name: str
    table_count: int


@dataclass
class DashboardStats:
    error_count: int
    warning_count: int
    tables_monitored: int
    last_check_time: str | None


def _load_findings_json(findings_path: Path | None = None) -> dict:
    """Load the raw findings JSON data."""
    path = findings_path or get_default_findings_path()
    if not path.exists():
        return {}

    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_findings(
    findings_path: Path | None = None,
) -> tuple[list[Finding], str | None]:
    """Load findings from the JSON file. Returns (findings, generated_at)."""
    data = _load_findings_json(findings_path)
    if not data:
        return [], None

    findings = [
        Finding(
            check_type=f["check_type"],
            severity=f["severity"],
            schema_name=f["schema_name"],
            table_name=f["table_name"],
            description=f["description"],
            details=f.get("details", {}),
            connection_name=f.get("connection_name", ""),
        )
        for f in data.get("findings", [])
    ]
    return findings, data.get("generated_at")


def load_dbt_findings(findings_path: Path | None = None) -> list[DbtFinding]:
    """Load dbt findings from the JSON file."""
    data = _load_findings_json(findings_path)
    return [
        DbtFinding(
            resource_type=f["resource_type"],
            severity=f["severity"],
            unique_id=f["unique_id"],
            status=f["status"],
            execution_time=f["execution_time"],
            description=f["description"],
            details=f.get("details", {}),
        )
        for f in data.get("dbt_findings", [])
    ]


@dataclass
class DbtStats:
    error_count: int
    warning_count: int


def get_dbt_stats(dbt_findings: list[DbtFinding]) -> DbtStats:
    """Compute summary stats for dbt findings."""
    return DbtStats(
        error_count=sum(1 for f in dbt_findings if f.severity == "error"),
        warning_count=sum(1 for f in dbt_findings if f.severity == "warning"),
    )


@dataclass
class UsageStats:
    unused_count: int
    stale_count: int
    total_cost_usd: float | None


def get_usage_findings(findings: list[Finding]) -> list[Finding]:
    """Filter findings to usage check type, sorted by severity (errors first)."""
    usage = [f for f in findings if f.check_type == "usage"]
    severity_order = {"error": 0, "warning": 1}
    return sorted(usage, key=lambda f: severity_order.get(f.severity, 2))


def get_usage_stats(
    usage_findings: list[Finding], cost_summary: dict | None
) -> UsageStats:
    """Compute summary stats for the usage page."""
    return UsageStats(
        unused_count=sum(1 for f in usage_findings if f.severity == "error"),
        stale_count=sum(1 for f in usage_findings if f.severity == "warning"),
        total_cost_usd=cost_summary["total_cost_usd"] if cost_summary else None,
    )


def load_cost_summary(findings_path: Path | None = None) -> dict | None:
    """Load cost_summary from the findings JSON, if present."""
    data = _load_findings_json(findings_path)
    return data.get("cost_summary")


def get_stats(
    findings: list[Finding],
    generated_at: str | None,
    state_db: BaseStateStore,
    connection_name: str = "",
) -> DashboardStats:
    """Compute summary stats for the dashboard."""
    tables = state_db.get_latest_schema(connection_name)
    return DashboardStats(
        error_count=sum(1 for f in findings if f.severity == "error"),
        warning_count=sum(1 for f in findings if f.severity == "warning"),
        tables_monitored=len(tables),
        last_check_time=generated_at,
    )


def get_volume_timeseries(
    state_db: BaseStateStore,
    schema_name: str,
    table_name: str,
    depth: int = 30,
    connection_name: str = "",
) -> list[dict]:
    """Get volume history as a list of dicts for charting."""
    rows = state_db.get_volume_timeseries(schema_name, table_name, depth, connection_name)
    return [{"snapshot": ts, "row_count": count} for ts, count in rows]


def get_table_info(
    state_db: BaseStateStore, schema_name: str, table_name: str, connection_name: str = ""
) -> TableInfo | None:
    """Get schema info for a specific table from the latest snapshot."""
    tables = state_db.get_latest_schema(connection_name)
    for t in tables:
        if t.schema_name == schema_name and t.table_name == table_name:
            return t
    return None


def get_volume_stats(
    state_db: BaseStateStore,
    schema_name: str,
    table_name: str,
    depth: int = 30,
    connection_name: str = "",
) -> VolumeStats:
    """Compute volume statistics from snapshot history."""
    counts = state_db.get_volume_history(schema_name, table_name, depth, connection_name)

    if not counts:
        return VolumeStats(None, None, None, None, None, None, None, 0)
    current = counts[0]
    previous = counts[1] if len(counts) > 1 else None
    delta = current - previous if previous is not None else None
    delta_pct = (
        (delta / previous * 100)
        if delta is not None and previous is not None and previous != 0
        else None
    )

    return VolumeStats(
        current=current,
        previous=previous,
        delta=delta,
        delta_pct=round(delta_pct, 1) if delta_pct is not None else None,
        minimum=min(counts),
        maximum=max(counts),
        average=round(sum(counts) / len(counts), 1),
        snapshot_count=len(counts),
    )


def get_table_history(
    state_db: BaseStateStore, schema_name: str, table_name: str, connection_name: str = ""
) -> TableHistory:
    """Get first-seen date and snapshot count for a table."""
    first_seen, snapshot_count = state_db.get_table_first_seen(
        schema_name, table_name, connection_name
    )

    if first_seen is None:
        return TableHistory(first_seen=None, snapshot_count=0)

    return TableHistory(
        first_seen=first_seen[:16].replace("T", " "),
        snapshot_count=snapshot_count,
    )


def get_schema_diff(
    state_db: BaseStateStore,
    schema_name: str,
    table_name: str,
    connection_name: str = "",
) -> SchemaDiff | None:
    """Compare schema between the two most recent snapshots."""
    snapshot_ids = state_db.get_recent_snapshot_ids_for_table(
        schema_name, table_name, limit=2, connection_name=connection_name
    )

    if len(snapshot_ids) < 2:
        return None

    current_id, previous_id = snapshot_ids[0], snapshot_ids[1]

    current_cols = state_db.get_columns_for_snapshot(
        current_id, schema_name, table_name
    )
    previous_cols = state_db.get_columns_for_snapshot(
        previous_id, schema_name, table_name
    )

    added = [
        ColumnInfo(name, dtype, nullable)
        for name, (dtype, nullable) in current_cols.items()
        if name not in previous_cols
    ]
    removed = [
        ColumnInfo(name, dtype, nullable)
        for name, (dtype, nullable) in previous_cols.items()
        if name not in current_cols
    ]

    type_changes = []
    nullable_changes = []
    for name in current_cols:
        if name in previous_cols:
            cur_type, cur_null = current_cols[name]
            prev_type, prev_null = previous_cols[name]
            if cur_type != prev_type:
                type_changes.append((name, prev_type, cur_type))
            if cur_null != prev_null:
                nullable_changes.append((name, prev_null, cur_null))

    if not added and not removed and not type_changes and not nullable_changes:
        return None

    return SchemaDiff(
        added=added,
        removed=removed,
        type_changes=type_changes,
        nullable_changes=nullable_changes,
    )


def get_findings_stats(findings: list[Finding]) -> FindingsStats:
    """Compute summary statistics for findings."""
    error_count = sum(1 for f in findings if f.severity == "error")
    warning_count = sum(1 for f in findings if f.severity == "warning")

    # Group by check_type
    by_check_type: dict[str, tuple[int, int]] = {}
    for f in findings:
        errors, warnings = by_check_type.get(f.check_type, (0, 0))
        if f.severity == "error":
            by_check_type[f.check_type] = (errors + 1, warnings)
        else:
            by_check_type[f.check_type] = (errors, warnings + 1)

    # Group by connection
    by_connection: dict[str, tuple[int, int]] = {}
    for f in findings:
        conn = f.connection_name or "default"
        errors, warnings = by_connection.get(conn, (0, 0))
        if f.severity == "error":
            by_connection[conn] = (errors + 1, warnings)
        else:
            by_connection[conn] = (errors, warnings + 1)

    return FindingsStats(
        total_count=len(findings),
        error_count=error_count,
        warning_count=warning_count,
        by_check_type=by_check_type,
        by_connection=by_connection,
    )


def filter_findings(
    findings: list[Finding],
    check_type: str = "",
    severity: str = "",
    schema_name: str = "",
    connection: str = "",
    q: str = "",
) -> list[Finding]:
    """Filter findings by multiple criteria."""
    result = findings

    if check_type:
        result = [f for f in result if f.check_type == check_type]
    if severity:
        result = [f for f in result if f.severity == severity]
    if schema_name:
        result = [f for f in result if f.schema_name == schema_name]
    if connection:
        result = [f for f in result if (f.connection_name or "default") == connection]
    if q:
        needle = q.lower()
        result = [
            f
            for f in result
            if needle in f.description.lower()
            or needle in f.table_name.lower()
            or needle in f.schema_name.lower()
        ]

    return result


def get_snapshot_history(
    state_db: BaseStateStore, days: int, connection_name: str = ""
) -> list[SnapshotInfo]:
    """Get recent snapshots with metadata."""
    # Query snapshots table for recent entries
    # This is a simplified implementation - we'll need to add this to BaseStateStore if not already present
    # For now, we'll return an empty list and implement the actual query when we have access to the state DB
    # TODO: Add get_recent_snapshots method to BaseStateStore
    return []


def get_cost_timeseries(
    state_db: BaseStateStore, depth: int, connection_name: str = ""
) -> list[dict]:
    """Get cost trend data for charting."""
    cost_history = state_db.get_cost_history(depth, connection_name)
    return [{"snapshot": ts, "cost": cost} for ts, cost in cost_history]


def get_findings_by_connection(findings: list[Finding]) -> dict[str, tuple[int, int]]:
    """Group findings by connection_name."""
    result = {}
    for f in findings:
        conn = f.connection_name or "default"
        errors, warnings = result.get(conn, (0, 0))
        if f.severity == "error":
            result[conn] = (errors + 1, warnings)
        else:
            result[conn] = (errors, warnings + 1)
    return result


def get_critical_findings(findings: list[Finding], limit: int = 5) -> list[Finding]:
    """Get top N critical findings (errors first, sorted by importance)."""
    errors = [f for f in findings if f.severity == "error"]
    # Sort by check type priority: volume > schema > freshness > integrity
    priority = {"volume": 0, "schema": 1, "freshness": 2, "integrity": 3}
    errors.sort(key=lambda f: priority.get(f.check_type, 99))
    return errors[:limit]


def get_findings_by_table(findings: list[Finding]) -> dict[tuple[str, str], tuple[int, int]]:
    """Group findings by (schema, table)."""
    result = {}
    for f in findings:
        key = (f.schema_name, f.table_name)
        errors, warnings = result.get(key, (0, 0))
        if f.severity == "error":
            result[key] = (errors + 1, warnings)
        else:
            result[key] = (errors, warnings + 1)
    return result
