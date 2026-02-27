from __future__ import annotations

import dataclasses
from contextlib import contextmanager
from typing import Any, Generator

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from olly.dashboard.data import (
    filter_findings,
    get_cost_daily_timeseries,
    get_dbt_stats,
    get_findings_by_connection,
    get_findings_by_table,
    get_findings_stats,
    get_findings_trend,
    get_least_used_tables,
    get_previous_stats,
    get_schema_diff,
    get_snapshot_history,
    get_stats,
    get_table_history,
    get_table_info,
    get_usage_findings,
    get_usage_stats,
    get_volume_stats,
    get_volume_timeseries,
    load_cost_summary,
    load_dbt_findings_from_db,
    load_findings_from_db,
)
from olly.config import load_config
from olly.state import BaseStateStore, open_state

router = APIRouter(prefix="/api")


def _dc(obj: Any) -> Any:
    """Convert dataclasses (and lists/dicts of them) to plain dicts."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, list):
        return [_dc(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _dc(v) for k, v in obj.items()}
    return obj


def _get_current_connection(connection_param: str = "") -> str:
    config = load_config()
    if connection_param and connection_param in config.connections:
        return connection_param
    return next(iter(config.connections.keys()))


@contextmanager
def _state_db(
    connection_name: str = "",
) -> Generator[tuple[BaseStateStore, str], None, None]:
    config = load_config()
    conn_name = _get_current_connection(connection_name)
    nc = config.connections[conn_name]
    from olly.adapter import connect_typed

    adapter = connect_typed(nc.connection)
    with open_state(config, adapter) as state_db:
        yield state_db, conn_name


def _get_all_connections() -> list[str]:
    from olly.dashboard.data import get_all_connections

    return get_all_connections()


@router.get("/connections")
def api_connections():
    connections = _get_all_connections()
    current = connections[0] if connections else ""
    return {"connections": connections, "current": current}


@router.get("/overview")
def api_overview(connection: str = Query("")):
    conn_name = _get_current_connection(connection)
    with _state_db(conn_name) as (state_db, conn_name):
        findings = load_findings_from_db(state_db)
        dbt_findings = load_dbt_findings_from_db(state_db)
        stats = get_stats(findings, state_db, conn_name)
        findings_trend = get_findings_trend(state_db)
        prev = get_previous_stats(state_db)
        findings_by_table_map = get_findings_by_table(findings)
        table_rows = _build_table_rows(state_db, conn_name, findings_by_table_map)

    dbt_stats = get_dbt_stats(dbt_findings)

    findings_by_connection = get_findings_by_connection(findings)
    fbc = {
        conn: {"errors": e, "warnings": w}
        for conn, (e, w) in findings_by_connection.items()
    }

    # Top tables with issues, sorted by errors desc then warnings desc
    top_tables = sorted(
        [r for r in table_rows if r["error_count"] > 0 or r["warning_count"] > 0],
        key=lambda r: (-r["error_count"], -r["warning_count"]),
    )[:5]

    prev_stats = (
        {"error_count": prev[0], "warning_count": prev[1]} if prev else None
    )

    return {
        "stats": _dc(stats),
        "dbt_stats": _dc(dbt_stats),
        "findings_by_connection": fbc,
        "findings_trend": _dc(findings_trend),
        "top_tables": top_tables,
        "prev_stats": prev_stats,
    }


@router.get("/findings")
def api_findings(
    connection: str = Query(""),
    check_type: str = Query(""),
    severity: str = Query(""),
    schema: str = Query(""),
    q: str = Query(""),
    page: int = Query(1, ge=1),
):
    conn_name = _get_current_connection(connection)
    with _state_db(conn_name) as (state_db, conn_name):
        findings = load_findings_from_db(state_db)
        last_check_time = state_db.get_last_check_time()

    filtered = filter_findings(findings, check_type, severity, schema, connection, q)
    stats = get_findings_stats(filtered)

    per_page = 50
    total = len(filtered)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    page_findings = filtered[start : start + per_page]

    check_types = sorted({f.check_type for f in findings})
    severities = sorted({f.severity for f in findings})
    schemas = sorted({f.schema_name for f in findings})

    return {
        "findings": _dc(page_findings),
        "stats": _dc(stats),
        "filters": {
            "check_types": check_types,
            "severities": severities,
            "schemas": schemas,
        },
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "last_check_time": last_check_time,
    }


TABLES_PER_PAGE = 50


def _build_table_rows(
    state_db: BaseStateStore,
    connection_name: str = "",
    findings_by_table: dict[tuple[str, str], tuple[int, int]] | None = None,
) -> list[dict]:
    all_tables = state_db.get_latest_schema(connection_name)
    volumes = state_db.get_latest_volume(connection_name)
    volume_map = {(v.schema_name, v.table_name): v.row_count for v in volumes}
    findings_map = findings_by_table or {}
    return [
        {
            "schema": t.schema_name,
            "table": t.table_name,
            "type": t.table_type,
            "columns": len(t.columns),
            "row_count": volume_map.get((t.schema_name, t.table_name)),
            "error_count": findings_map.get((t.schema_name, t.table_name), (0, 0))[0],
            "warning_count": findings_map.get((t.schema_name, t.table_name), (0, 0))[
                1
            ],
        }
        for t in all_tables
    ]


def _filter_sort_paginate(
    table_rows: list[dict],
    search: str,
    sort: str,
    order: str,
    page: int,
) -> tuple[list[dict], int]:
    if search:
        q = search.lower()
        table_rows = [
            r
            for r in table_rows
            if q in r["schema"].lower()
            or q in r["table"].lower()
            or q in r["type"].lower()
        ]

    sort_key = (
        sort
        if sort in ("schema", "table", "type", "columns", "row_count")
        else "table"
    )
    reverse = order == "desc"
    table_rows = sorted(
        table_rows,
        key=lambda r: (
            r[sort_key] is None,
            r[sort_key] or 0
            if sort_key in ("columns", "row_count")
            else (r[sort_key] or ""),
        ),
        reverse=reverse,
    )

    total = len(table_rows)
    start = (page - 1) * TABLES_PER_PAGE
    return table_rows[start : start + TABLES_PER_PAGE], total


@router.get("/tables")
def api_tables(
    connection: str = Query(""),
    search: str = Query(""),
    sort: str = Query("table"),
    order: str = Query("asc"),
    page: int = Query(1, ge=1),
):
    conn_name = _get_current_connection(connection)
    with _state_db(conn_name) as (state_db, conn_name):
        findings = load_findings_from_db(state_db)
        findings_by_table_map = get_findings_by_table(findings)
        table_rows = _build_table_rows(state_db, conn_name, findings_by_table_map)

    page_rows, total = _filter_sort_paginate(table_rows, search, sort, order, page)
    total_pages = max(1, (total + TABLES_PER_PAGE - 1) // TABLES_PER_PAGE)

    return {
        "tables": page_rows,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    }


@router.get("/table/{schema}/{table}")
def api_table_detail(schema: str, table: str, connection: str = Query("")):
    conn_name = _get_current_connection(connection)
    with _state_db(conn_name) as (state_db, conn_name):
        findings = load_findings_from_db(state_db)
        table_findings = [
            f for f in findings if f.schema_name == schema and f.table_name == table
        ]
        table_info = get_table_info(state_db, schema, table, conn_name)
        timeseries = get_volume_timeseries(
            state_db, schema, table, connection_name=conn_name
        )
        vol_stats = get_volume_stats(state_db, schema, table, connection_name=conn_name)
        history = get_table_history(state_db, schema, table, conn_name)
        schema_diff = get_schema_diff(state_db, schema, table, conn_name)

    return {
        "table_info": _dc(table_info),
        "findings": _dc(table_findings),
        "volume_stats": _dc(vol_stats),
        "volume_timeseries": timeseries,
        "history": _dc(history),
        "schema_diff": _dc(schema_diff),
    }


@router.get("/history")
def api_history(connection: str = Query(""), days: int = Query(30)):
    conn_name = _get_current_connection(connection)
    with _state_db(conn_name) as (state_db, conn_name):
        snapshots = get_snapshot_history(state_db, days, conn_name)

    return {"snapshots": _dc(snapshots), "days": days}


@router.get("/usage")
def api_usage(connection: str = Query("")):
    conn_name = _get_current_connection(connection)
    with _state_db(conn_name) as (state_db, conn_name):
        findings = load_findings_from_db(state_db)
        cost_daily = get_cost_daily_timeseries(
            state_db, days=30, connection_name=conn_name
        )
        least_used = get_least_used_tables(state_db, conn_name)

    cost_summary = load_cost_summary()
    usage_findings = get_usage_findings(findings)
    stats = get_usage_stats(usage_findings, cost_summary)

    return {
        "stats": _dc(stats),
        "usage_findings": _dc(usage_findings),
        "cost_summary": cost_summary,
        "cost_daily": cost_daily,
        "least_used": _dc(least_used),
    }


@router.get("/dbt")
def api_dbt(connection: str = Query("")):
    conn_name = _get_current_connection(connection)
    with _state_db(conn_name) as (state_db, _conn):
        dbt_findings = load_dbt_findings_from_db(state_db)

    dbt_stats = get_dbt_stats(dbt_findings)
    resource_types = sorted({f.resource_type for f in dbt_findings})
    severities = sorted({f.severity for f in dbt_findings})

    return {
        "dbt_stats": _dc(dbt_stats),
        "dbt_findings": _dc(dbt_findings),
        "resource_types": resource_types,
        "severities": severities,
    }


@router.post("/refresh")
def api_refresh():
    from olly.cli.check import run_checks
    from olly.config import load_config as _load_config
    from olly.results import write_findings_json

    config = _load_config()
    findings, dbt_findings, cost_records = run_checks(config)
    write_findings_json(findings, dbt_findings=dbt_findings, cost_records=cost_records)

    return JSONResponse({"success": True})
