from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from olly.dashboard.charts import (
    cost_by_day_chart,
    volume_trend_chart,
)
from olly.dashboard.data import (
    filter_findings,
    get_cost_daily_timeseries,
    get_critical_findings,
    get_dbt_stats,
    get_findings_by_connection,
    get_findings_by_table,
    get_findings_stats,
    get_least_used_tables,
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

DASHBOARD_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=DASHBOARD_DIR / "templates")

router = APIRouter()


def _get_current_connection(connection_param: str = "") -> str:
    """Get current connection from parameter or default to first."""
    config = load_config()
    if connection_param and connection_param in config.connections:
        return connection_param
    return next(iter(config.connections.keys()))


@contextmanager
def _state_db(connection_name: str = "") -> Generator[tuple[BaseStateStore, str], None, None]:
    config = load_config()
    conn_name = _get_current_connection(connection_name)
    nc = config.connections[conn_name]
    from olly.adapter import connect_typed

    adapter = connect_typed(nc.connection)
    with open_state(config, adapter) as state_db:
        yield state_db, conn_name


@router.get("/", response_class=HTMLResponse)
def index(request: Request, connection: str = Query("")):
    from olly.dashboard.data import get_all_connections

    conn_name = _get_current_connection(connection)
    with _state_db(conn_name) as (state_db, conn_name):
        findings = load_findings_from_db(state_db)
        dbt_findings = load_dbt_findings_from_db(state_db)
        stats = get_stats(findings, state_db, conn_name)
    dbt_stats = get_dbt_stats(dbt_findings)
    dbt_issue_findings = [f for f in dbt_findings if f.severity != "pass"]

    check_types = sorted({f.check_type for f in findings})
    severities = sorted({f.severity for f in findings})
    schemas = sorted({f.schema_name for f in findings})

    # Build per-check-type breakdown: [(check_type, error_count, warning_count), ...]
    check_counts: dict[str, dict[str, int]] = {}
    for f in findings:
        check_counts.setdefault(f.check_type, {"error": 0, "warning": 0})
        check_counts[f.check_type][f.severity] = (
            check_counts[f.check_type].get(f.severity, 0) + 1
        )
    check_breakdown = [
        (ct, counts["error"], counts["warning"])
        for ct, counts in sorted(check_counts.items())
    ]

    # Get findings by connection and critical findings
    findings_by_connection = get_findings_by_connection(findings)
    critical_findings = get_critical_findings(findings, limit=5)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "stats": stats,
            "dbt_stats": dbt_stats,
            "dbt_findings": dbt_issue_findings,
            "findings": findings,
            "check_breakdown": check_breakdown,
            "check_types": check_types,
            "severities": severities,
            "schemas": schemas,
            "findings_by_connection": findings_by_connection,
            "critical_findings": critical_findings,
            "connections": get_all_connections(),
            "current_connection": conn_name,
        },
    )


@router.get("/findings", response_class=HTMLResponse)
def findings_page(
    request: Request,
    connection: str = Query(""),
    check_type: str = Query(""),
    severity: str = Query(""),
    schema_name: str = Query("", alias="schema"),
    q: str = Query(""),
    page: int = Query(1, ge=1),
):
    from olly.dashboard.data import get_all_connections

    conn_name = _get_current_connection(connection)
    with _state_db(conn_name) as (state_db, conn_name):
        findings = load_findings_from_db(state_db)
        last_check_time = state_db.get_last_check_time()

    # Apply filters
    filtered_findings = filter_findings(
        findings, check_type, severity, schema_name, connection, q
    )

    # Compute stats on filtered findings
    stats = get_findings_stats(filtered_findings)

    # Paginate
    findings_per_page = 50
    total = len(filtered_findings)
    total_pages = max(1, (total + findings_per_page - 1) // findings_per_page)
    start = (page - 1) * findings_per_page
    page_findings = filtered_findings[start : start + findings_per_page]

    # Get unique values for filter dropdowns
    check_types = sorted({f.check_type for f in findings})
    severities = sorted({f.severity for f in findings})
    schemas = sorted({f.schema_name for f in findings})
    connections_list = sorted({f.connection_name or "default" for f in findings})

    ctx = {
        "findings": page_findings,
        "stats": stats,
        "generated_at": last_check_time,
        "check_type": check_type,
        "severity": severity,
        "schema_name": schema_name,
        "q": q,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "check_types": check_types,
        "severities": severities,
        "schemas": schemas,
        "connections_list": connections_list,
        "connections": get_all_connections(),
        "current_connection": conn_name,
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "partials/findings_rows.html", ctx)
    return templates.TemplateResponse(request, "findings.html", ctx)


@router.get("/history", response_class=HTMLResponse)
def history_page(
    request: Request,
    connection: str = Query(""),
    days: int = Query(30),
):
    from olly.dashboard.data import get_all_connections

    conn_name = _get_current_connection(connection)

    with _state_db(conn_name) as (state_db, conn_name):
        snapshots = get_snapshot_history(state_db, days, conn_name)

    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "snapshots": snapshots,
            "days": days,
            "connections": get_all_connections(),
            "current_connection": conn_name,
        },
    )


@router.get("/api/findings", response_class=HTMLResponse)
def api_findings(
    request: Request,
    check_type: str = Query("", alias="check_type"),
    severity: str = Query("", alias="severity"),
    schema_name: str = Query("", alias="schema"),
    q: str = Query("", alias="q"),
):
    with _state_db() as (state_db, _conn):
        findings = load_findings_from_db(state_db)

    findings = filter_findings(findings, check_type, severity, schema_name, q=q)

    return templates.TemplateResponse(
        request,
        "partials/findings_rows.html",
        {"findings": findings},
    )


@router.get("/usage", response_class=HTMLResponse)
def usage(request: Request, connection: str = Query("")):
    from olly.dashboard.data import get_all_connections

    conn_name = _get_current_connection(connection)
    with _state_db(conn_name) as (state_db, conn_name):
        findings = load_findings_from_db(state_db)
        cost_daily = get_cost_daily_timeseries(state_db, days=30, connection_name=conn_name)
        least_used = get_least_used_tables(state_db, conn_name)
    cost_summary = load_cost_summary()
    usage_findings = get_usage_findings(findings)
    stats = get_usage_stats(usage_findings, cost_summary)

    cost_daily_chart_spec = None
    if cost_daily:
        cost_daily_chart_spec = json.dumps(cost_by_day_chart(cost_daily))

    return templates.TemplateResponse(
        request,
        "usage.html",
        {
            "stats": stats,
            "usage_findings": usage_findings,
            "cost_summary": cost_summary,
            "cost_daily_chart_spec": cost_daily_chart_spec,
            "least_used": least_used,
            "connections": get_all_connections(),
            "current_connection": conn_name,
        },
    )


@router.get("/dbt", response_class=HTMLResponse)
def dbt(request: Request, connection: str = Query("")):
    from olly.dashboard.data import get_all_connections

    conn_name = _get_current_connection(connection)
    with _state_db(conn_name) as (state_db, _conn):
        dbt_findings = load_dbt_findings_from_db(state_db)
    dbt_stats = get_dbt_stats(dbt_findings)

    resource_types = sorted({f.resource_type for f in dbt_findings})
    severities = sorted({f.severity for f in dbt_findings})

    return templates.TemplateResponse(
        request,
        "dbt.html",
        {
            "dbt_stats": dbt_stats,
            "dbt_findings": dbt_findings,
            "resource_types": resource_types,
            "severities": severities,
            "connections": get_all_connections(),
            "current_connection": conn_name,
        },
    )


@router.get("/api/dbt-findings", response_class=HTMLResponse)
def api_dbt_findings(
    request: Request,
    resource_type: str = Query("", alias="resource_type"),
    severity: str = Query("", alias="severity"),
):
    with _state_db() as (state_db, _conn):
        dbt_findings = load_dbt_findings_from_db(state_db)

    if resource_type:
        dbt_findings = [f for f in dbt_findings if f.resource_type == resource_type]
    if severity:
        dbt_findings = [f for f in dbt_findings if f.severity == severity]

    return templates.TemplateResponse(
        request,
        "partials/dbt_findings_rows.html",
        {"dbt_findings": dbt_findings},
    )


@router.get("/table/{schema}/{table}", response_class=HTMLResponse)
def table_detail(request: Request, schema: str, table: str, connection: str = Query("")):
    from olly.dashboard.data import get_all_connections

    conn_name = _get_current_connection(connection)

    with _state_db(conn_name) as (state_db, conn_name):
        findings = load_findings_from_db(state_db)
        table_findings = [
            f for f in findings if f.schema_name == schema and f.table_name == table
        ]
        table_info = get_table_info(state_db, schema, table, conn_name)
        timeseries = get_volume_timeseries(state_db, schema, table, connection_name=conn_name)
        chart_spec = volume_trend_chart(timeseries) if timeseries else None
        vol_stats = get_volume_stats(state_db, schema, table, connection_name=conn_name)
        history = get_table_history(state_db, schema, table, conn_name)
        schema_diff = get_schema_diff(state_db, schema, table, conn_name)

    return templates.TemplateResponse(
        request,
        "table_detail.html",
        {
            "schema": schema,
            "table": table,
            "findings": table_findings,
            "table_info": table_info,
            "chart_spec": json.dumps(chart_spec) if chart_spec else None,
            "vol_stats": vol_stats,
            "history": history,
            "schema_diff": schema_diff,
            "connections": get_all_connections(),
            "current_connection": conn_name,
        },
    )


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
            "warning_count": findings_map.get((t.schema_name, t.table_name), (0, 0))[1],
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
    """Filter, sort, and paginate table rows. Returns (page_rows, total_count)."""
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
        sort if sort in ("schema", "table", "type", "columns", "row_count") else "table"
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


@router.get("/tables", response_class=HTMLResponse)
def tables(
    request: Request,
    connection: str = Query(""),
    search: str = Query(""),
    sort: str = Query("table"),
    order: str = Query("asc"),
    page: int = Query(1, ge=1),
):
    from olly.dashboard.data import get_all_connections

    conn_name = _get_current_connection(connection)

    # Load findings for status indicators
    with _state_db(conn_name) as (state_db, conn_name):
        findings = load_findings_from_db(state_db)
        findings_by_table_map = get_findings_by_table(findings)
        table_rows = _build_table_rows(state_db, conn_name, findings_by_table_map)

    page_rows, total = _filter_sort_paginate(table_rows, search, sort, order, page)
    total_pages = max(1, (total + TABLES_PER_PAGE - 1) // TABLES_PER_PAGE)

    ctx = {
        "table_rows": page_rows,
        "search": search,
        "sort": sort,
        "order": order,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "connections": get_all_connections(),
        "current_connection": conn_name,
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "partials/tables_body.html", ctx)
    return templates.TemplateResponse(request, "tables.html", ctx)


@router.post("/refresh", response_class=HTMLResponse)
def refresh(request: Request):
    from olly.cli.check import run_checks
    from olly.config import load_config
    from olly.results import write_findings_json

    config = load_config()
    findings, dbt_findings, cost_records = run_checks(config)
    write_findings_json(findings, dbt_findings=dbt_findings, cost_records=cost_records)

    return api_findings(request)
