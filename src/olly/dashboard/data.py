from __future__ import annotations

from dataclasses import dataclass

from olly.config import load_config
from olly.models import ColumnInfo, DbtFinding, Finding, TableInfo
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
    not_started_count: int = 0
    in_progress_count: int = 0
    no_action_count: int = 0
    completed_count: int = 0


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


def load_findings_from_db(
    state_db: BaseStateStore, connection_name: str | None = None
) -> list[Finding]:
    """Load findings from the most recent check run."""
    return state_db.get_latest_findings(connection_name=connection_name)


def load_dbt_findings_from_db(state_db: BaseStateStore) -> list[DbtFinding]:
    """Load dbt findings from the most recent check run."""
    return state_db.get_latest_dbt_findings()


@dataclass
class DbtStats:
    error_count: int
    warning_count: int
    pass_count: int
    total_count: int
    total_execution_time: float = 0.0
    total_failures: int = 0


def get_dbt_stats(dbt_findings: list[DbtFinding]) -> DbtStats:
    """Compute summary stats for dbt findings."""
    total_failures = 0
    for f in dbt_findings:
        failures = f.details.get("failures")
        if isinstance(failures, int):
            total_failures += failures
    return DbtStats(
        error_count=sum(1 for f in dbt_findings if f.severity == "error"),
        warning_count=sum(1 for f in dbt_findings if f.severity == "warning"),
        pass_count=sum(1 for f in dbt_findings if f.severity == "pass"),
        total_count=len(dbt_findings),
        total_execution_time=sum(f.execution_time for f in dbt_findings),
        total_failures=total_failures,
    )


@dataclass
class DbtExecutionLeaderboardEntry:
    unique_id: str
    resource_type: str
    execution_time: float
    status: str
    severity: str


def get_dbt_execution_leaderboard(
    dbt_findings: list[DbtFinding], limit: int = 20,
) -> list[DbtExecutionLeaderboardEntry]:
    """Return the slowest dbt nodes sorted by execution time descending."""
    sorted_findings = sorted(dbt_findings, key=lambda f: f.execution_time, reverse=True)
    return [
        DbtExecutionLeaderboardEntry(
            unique_id=f.unique_id,
            resource_type=f.resource_type,
            execution_time=f.execution_time,
            status=f.status,
            severity=f.severity,
        )
        for f in sorted_findings[:limit]
    ]


@dataclass
class DbtRunHistoryPoint:
    created_at: str
    elapsed_time: float
    total_nodes: int
    error_count: int
    warning_count: int
    pass_count: int


def get_dbt_run_history(
    state_db: BaseStateStore, limit: int = 30,
) -> list[DbtRunHistoryPoint]:
    """Get dbt run history for charting, oldest first."""
    rows = state_db.get_dbt_run_history_with_timestamps(limit)
    # rows come newest-first, reverse for chronological chart display
    return [
        DbtRunHistoryPoint(
            created_at=ts,
            elapsed_time=run.elapsed_time,
            total_nodes=run.total_nodes,
            error_count=run.error_count,
            warning_count=run.warning_count,
            pass_count=run.pass_count,
        )
        for ts, run in reversed(rows)
    ]


def get_dbt_node_timeseries(
    state_db: BaseStateStore, unique_id: str, limit: int = 30,
) -> list[dict]:
    """Get execution time history for a specific dbt node."""
    rows = state_db.get_dbt_node_timing_timeseries(unique_id, limit)
    return [{"timestamp": ts, "execution_time": t} for ts, t in rows]


@dataclass
class UsageStats:
    unused_count: int
    stale_count: int
    unused_schema_count: int
    total_cost_usd: float | None


def _is_schema_scope(finding: Finding) -> bool:
    return finding.details.get("scope") == "schema"


def get_usage_findings(findings: list[Finding]) -> list[Finding]:
    """Filter findings to usage check type.

    Schema-level rollup findings sort first, then by severity (errors first).
    """
    usage = [f for f in findings if f.check_type == "usage"]
    severity_order = {"error": 0, "warning": 1}
    return sorted(
        usage,
        key=lambda f: (
            0 if _is_schema_scope(f) else 1,
            severity_order.get(f.severity, 2),
        ),
    )


def get_usage_stats(
    usage_findings: list[Finding], cost_summary: dict | None
) -> UsageStats:
    """Compute summary stats for the usage page.

    Unused vs. stale is determined by ``details.last_queried_at`` (absent
    for unused tables), matching how the UI badges findings — severity is
    a single configured value for all usage findings, so it can't
    distinguish the two. Schema-level rollup findings are counted
    separately from per-table counts.
    """
    table_findings = [f for f in usage_findings if not _is_schema_scope(f)]
    unused = sum(
        1 for f in table_findings if f.details.get("last_queried_at") is None
    )
    return UsageStats(
        unused_count=unused,
        stale_count=len(table_findings) - unused,
        unused_schema_count=sum(1 for f in usage_findings if _is_schema_scope(f)),
        total_cost_usd=cost_summary["total_cost_usd"] if cost_summary else None,
    )


def build_cost_summary(
    state_db: BaseStateStore, connection_name: str = "",
) -> dict | None:
    """Build cost summary from cost records in the state database."""
    records = state_db.get_latest_cost(connection_name)
    if not records:
        return None

    total_cost = sum(r.estimated_cost_usd for r in records)

    # Aggregate by table
    table_agg: dict[tuple[str, str], float] = {}
    for r in records:
        key = (r.schema_name, r.table_name)
        table_agg[key] = table_agg.get(key, 0.0) + r.estimated_cost_usd
    top_tables = sorted(
        [{"schema": s, "table": t, "cost_usd": c} for (s, t), c in table_agg.items()],
        key=lambda x: -x["cost_usd"],
    )[:10]

    # Aggregate by user
    user_agg: dict[str, float] = {}
    for r in records:
        user_agg[r.user_email] = user_agg.get(r.user_email, 0.0) + r.estimated_cost_usd
    top_users = sorted(
        [{"user": u, "cost_usd": c} for u, c in user_agg.items()],
        key=lambda x: -x["cost_usd"],
    )[:10]

    return {
        "total_cost_usd": total_cost,
        "top_tables": top_tables,
        "top_users": top_users,
    }


def get_stats(
    findings: list[Finding],
    state_db: BaseStateStore,
    connection_name: str = "",
) -> DashboardStats:
    """Compute summary stats for the dashboard."""
    tables = state_db.get_latest_schema(connection_name)
    return DashboardStats(
        error_count=sum(1 for f in findings if f.severity == "error"),
        warning_count=sum(1 for f in findings if f.severity == "warning"),
        tables_monitored=len(tables),
        last_check_time=state_db.get_last_check_time(),
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


def hydrate_dispositions(
    findings: list[Finding], state_db: BaseStateStore,
) -> None:
    """Fill in the disposition field on each finding from the DB."""
    ids = [f.id for f in findings if f.id is not None]
    if not ids:
        return
    dispositions = state_db.get_current_dispositions(ids)
    for f in findings:
        if f.id is not None and f.id in dispositions:
            f.disposition = dispositions[f.id]


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
        not_started_count=sum(1 for f in findings if f.disposition == "not_started"),
        in_progress_count=sum(1 for f in findings if f.disposition == "in_progress"),
        no_action_count=sum(1 for f in findings if f.disposition == "no_action"),
        completed_count=sum(1 for f in findings if f.disposition == "completed"),
    )


def filter_findings(
    findings: list[Finding],
    check_type: str = "",
    severity: str = "",
    schema_name: str = "",
    connection: str = "",
    q: str = "",
    disposition: str = "",
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
    if disposition:
        result = [f for f in result if f.disposition == disposition]
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
    from olly.dashboard.queries import get_snapshot_history as _query_snapshot_history

    rows = _query_snapshot_history(state_db, days, connection_name)
    return [
        SnapshotInfo(
            snapshot_id=r[0],
            created_at=r[1],
            connection_name=r[2],
            table_count=r[3],
        )
        for r in rows
    ]


def get_cost_daily_timeseries(
    state_db: BaseStateStore, days: int, connection_name: str = ""
) -> list[dict]:
    """Get daily cost totals for charting."""
    daily = state_db.get_cost_daily(days, connection_name)
    return [{"day": day, "cost": cost} for day, cost in daily]


@dataclass
class LeastUsedTable:
    schema_name: str
    table_name: str
    query_count: int
    estimated_cost_usd: float


def get_least_used_tables(
    state_db: BaseStateStore, connection_name: str = "", limit: int = 10
) -> list[LeastUsedTable]:
    """Get the least-queried tables from the latest cost run."""
    records = state_db.get_latest_cost(connection_name)
    if not records:
        return []
    # Aggregate by table (records may have multiple users per table)
    table_agg: dict[tuple[str, str], tuple[int, float]] = {}
    for r in records:
        key = (r.schema_name, r.table_name)
        qc, cost = table_agg.get(key, (0, 0.0))
        table_agg[key] = (qc + r.query_count, cost + r.estimated_cost_usd)
    tables = [
        LeastUsedTable(
            schema_name=s, table_name=t, query_count=qc, estimated_cost_usd=cost
        )
        for (s, t), (qc, cost) in table_agg.items()
    ]
    tables.sort(key=lambda x: x.query_count)
    return tables[:limit]


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


@dataclass
class FindingsTrendPoint:
    timestamp: str
    errors: int
    warnings: int


def get_findings_trend(
    state_db: BaseStateStore, limit: int = 20
) -> list[FindingsTrendPoint]:
    """Return error/warning counts per day, using the latest run each day."""
    from olly.dashboard.queries import get_findings_trend as _query_findings_trend

    rows = _query_findings_trend(state_db, limit)
    return [
        FindingsTrendPoint(timestamp=r[0], errors=r[1], warnings=r[2])
        for r in reversed(rows)
    ]


def get_previous_stats(
    state_db: BaseStateStore,
) -> tuple[int, int] | None:
    """Return (errors, warnings) from the second-most-recent check run, or None."""
    from olly.dashboard.queries import get_previous_finding_counts

    return get_previous_finding_counts(state_db)


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
