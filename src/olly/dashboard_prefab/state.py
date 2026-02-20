from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from olly.config import load_config
from olly.dashboard.data import (
    get_dbt_stats,
    get_schema_diff,
    get_stats,
    get_table_history,
    get_usage_findings,
    get_usage_stats,
    get_volume_stats,
    get_volume_timeseries,
    load_cost_summary,
    load_dbt_findings,
    load_findings,
)
from olly.state import StateStore


def serialize_dataclass(obj):
    """Convert dataclasses to dicts recursively."""
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, list):
        return [serialize_dataclass(item) for item in obj]
    if isinstance(obj, dict):
        return {k: serialize_dataclass(v) for k, v in obj.items()}
    return obj


def build_table_details(
    state_db: StateStore,
    tables: list,
    findings: list,
    conn_name: str = "",
) -> dict:
    """Pre-load detail data for all tables.

    Returns a dict keyed by "schema.table" with detail data for each table.
    """
    details = {}
    for table in tables:
        key = f"{table.schema_name}.{table.table_name}"
        table_findings = [
            f for f in findings
            if f.schema_name == table.schema_name and f.table_name == table.table_name
        ]

        volume_stats = get_volume_stats(
            state_db, table.schema_name, table.table_name, depth=30, connection_name=conn_name
        )
        history = get_table_history(
            state_db, table.schema_name, table.table_name, connection_name=conn_name
        )
        timeseries = get_volume_timeseries(
            state_db, table.schema_name, table.table_name, depth=30, connection_name=conn_name
        )
        schema_diff = get_schema_diff(
            state_db, table.schema_name, table.table_name, connection_name=conn_name
        )

        details[key] = {
            "info": serialize_dataclass(table),
            "volume": serialize_dataclass(volume_stats),
            "history": serialize_dataclass(history),
            "timeseries": timeseries,  # Already a list of dicts
            "schema_diff": serialize_dataclass(schema_diff),
            "findings": serialize_dataclass(table_findings),
        }
    return details


def build_initial_state(findings_path: Path | None = None) -> dict:
    """Build initial state with all data loaded upfront."""
    config = load_config()

    # Get connection name (use first connection like original dashboard)
    conn_name = next(iter(config.connections.keys()))
    first_nc = config.connections[conn_name]

    # Open state store properly
    from olly.adapter import connect_typed
    from olly.state import open_state

    adapter = connect_typed(first_nc.connection)
    state_db = open_state(config, adapter, first_nc.connection.type)

    # Load findings data
    findings, generated_at = load_findings(findings_path)
    dbt_findings = load_dbt_findings(findings_path)
    cost_summary = load_cost_summary(findings_path)

    # Get stats (pass conn_name!)
    stats = get_stats(findings, generated_at, state_db, conn_name)
    dbt_stats = get_dbt_stats(dbt_findings)

    # Get usage-specific data
    usage_findings_list = get_usage_findings(findings)
    usage_stats = get_usage_stats(usage_findings_list, cost_summary)

    # Load tables list (pass conn_name!)
    tables = state_db.get_latest_schema(conn_name)
    tables_list = [
        {
            "schema": t.schema_name,
            "table": t.table_name,
            "type": t.table_type,
            "columns": len(t.columns),
            "row_count": None,  # Will be populated from volume records
        }
        for t in tables
    ]

    # Get row counts for tables (pass conn_name!)
    volume_records = state_db.get_latest_volume(conn_name)
    volume_map = {(v.schema_name, v.table_name): v.row_count for v in volume_records}
    for table in tables_list:
        key = (table["schema"], table["table"])
        if key in volume_map:
            table["row_count"] = volume_map[key]

    findings_serialized = serialize_dataclass(findings)
    dbt_findings_serialized = serialize_dataclass(dbt_findings)

    # Pre-load table details for all tables
    table_details = build_table_details(state_db, tables, findings, conn_name)

    # Compute check breakdown (errors/warnings per check type)
    check_counts: dict[str, dict[str, int]] = {}
    for f in findings:
        check_counts.setdefault(f.check_type, {"error": 0, "warning": 0})
        check_counts[f.check_type][f.severity] = (
            check_counts[f.check_type].get(f.severity, 0) + 1
        )

    # Build breakdown dict for easy template access
    check_breakdown = {
        "schema": {"errors": check_counts.get("schema", {}).get("error", 0), "warnings": check_counts.get("schema", {}).get("warning", 0)},
        "volume": {"errors": check_counts.get("volume", {}).get("error", 0), "warnings": check_counts.get("volume", {}).get("warning", 0)},
        "freshness": {"errors": check_counts.get("freshness", {}).get("error", 0), "warnings": check_counts.get("freshness", {}).get("warning", 0)},
        "integrity": {"errors": check_counts.get("integrity", {}).get("error", 0), "warnings": check_counts.get("integrity", {}).get("warning", 0)},
        "contracts": {"errors": check_counts.get("contracts", {}).get("error", 0), "warnings": check_counts.get("contracts", {}).get("warning", 0)},
    }

    # Default to first table for initial detail page
    default_table_key = list(table_details.keys())[0] if table_details else "main.orders"
    default_detail = table_details.get(default_table_key, {
        "info": {"table_type": "", "columns": []},
        "volume": {"current": None, "delta_pct": None, "minimum": None, "maximum": None, "average": None, "snapshot_count": 0},
        "history": {"first_seen": None, "snapshot_count": 0},
        "timeseries": [],
        "schema_diff": {"added": [], "removed": [], "type_changes": [], "nullable_changes": []},
        "findings": [],
    })

    return {
        # Navigation
        "page": "dashboard",
        # Core data
        "findings": findings_serialized,
        "dbt_findings": dbt_findings_serialized,
        "cost_summary": cost_summary or {},
        "tables": tables_list,
        "stats": {
            "error_count": stats.error_count,
            "warning_count": stats.warning_count,
            "tables_monitored": stats.tables_monitored,
            "last_check_time": stats.last_check_time or "",
            "dbt_error_count": dbt_stats.error_count,
            "dbt_warning_count": dbt_stats.warning_count,
        },
        # Debug counts
        "findings_count": len(findings_serialized),
        "dbt_findings_count": len(dbt_findings_serialized),
        "tables_count": len(tables_list),
        # Check breakdown
        "check_breakdown": check_breakdown,
        # Usage data
        "usage_findings": serialize_dataclass(usage_findings_list),
        "usage_stats": {
            "unused_count": usage_stats.unused_count,
            "stale_count": usage_stats.stale_count,
            "total_cost_usd": usage_stats.total_cost_usd or 0,
        },
        # Filters
        "filter_check_type": "",
        "filter_severity": "",
        "filter_schema": "",
        "filter_search": "",
        # Tables page state
        "tables_search": "",
        "tables_sort_by": "table",
        "tables_sort_order": "asc",
        "tables_page": 0,
        # Table detail state - flattened for current table
        "detail_schema": default_table_key.split('.')[0] if '.' in default_table_key else "",
        "detail_table": default_table_key.split('.')[1] if '.' in default_table_key else "",
        "detail_info": default_detail["info"],
        "detail_volume": default_detail["volume"],
        "detail_history": default_detail["history"],
        "detail_timeseries": default_detail["timeseries"],
        "detail_schema_diff": default_detail["schema_diff"],
        "detail_findings": default_detail["findings"],
        # Pre-loaded detail data lookup (keyed by "schema.table")
        "table_details": table_details,
    }
