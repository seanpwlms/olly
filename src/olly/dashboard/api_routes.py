from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from olly.dashboard.data import (
    filter_findings,
    get_cost_daily_timeseries,
    get_dbt_execution_leaderboard,
    get_dbt_node_timeseries,
    get_dbt_run_history,
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
    hydrate_dispositions,
    build_cost_summary,
    load_dbt_findings_from_db,
    load_findings_from_db,
)
from olly.dashboard.data_checks import get_contracts_page_data, get_integrity_page_data
from olly.dashboard.schemas import (
    ConnectionsResponse,
    ContractsResponse,
    ContractStatusModel,
    DashboardStatsModel,
    DbtExecutionLeaderboardModel,
    DbtFindingModel,
    DbtNodeTimingModel,
    DbtNodeTimingsResponse,
    DbtResponse,
    DbtRunHistoryPointModel,
    DbtStatsModel,
    DispositionCounts,
    DispositionHistoryResponse,
    FindingModel,
    FindingsByConnection,
    FindingsResponse,
    FindingsStatsModel,
    FindingsTrendPointModel,
    HistoryResponse,
    IntegrityResponse,
    LeastUsedTableModel,
    OverviewResponse,
    PrevStatsModel,
    SnapshotInfoModel,
    SyncStatusModel,
    TableCostModel,
    TableDetailResponse,
    TableHistoryModel,
    TableRowModel,
    TablesResponse,
    UsageResponse,
    UsageStatsModel,
    VolumeStatsModel,
    FiltersModel,
    CostUserModel,
    SchemaDiffModel,
    TableInfoModel,
)
from olly.config import OllyConfig, load_config
from olly.state import BaseStateStore, open_state

router = APIRouter(prefix="/api")

PAGE_SIZE = 50


def paginate(items: list, page: int) -> tuple[list, int, int]:
    """Return (page_items, total, total_pages) for a page of items."""
    total = len(items)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    start = (page - 1) * PAGE_SIZE
    return items[start : start + PAGE_SIZE], total, total_pages


def _get_current_connection(
    connection_param: str = "", config: OllyConfig | None = None,
) -> str:
    cfg = config or load_config()
    if connection_param and connection_param in cfg.connections:
        return connection_param
    return next(iter(cfg.connections.keys()))


@contextmanager
def _state_db(
    connection_name: str = "", config: OllyConfig | None = None,
) -> Generator[tuple[BaseStateStore, str], None, None]:
    cfg = config or load_config()
    conn_name = _get_current_connection(connection_name, cfg)
    nc = cfg.connections[conn_name]
    from olly.adapter import connect_typed

    adapter = connect_typed(nc.connection)
    with open_state(cfg, adapter) as state_db:
        yield state_db, conn_name


def _get_all_connections() -> list[str]:
    from olly.dashboard.data import get_all_connections

    return get_all_connections()


@router.get("/connections", response_model=ConnectionsResponse)
def api_connections():
    connections = _get_all_connections()
    current = connections[0] if connections else ""
    return ConnectionsResponse(connections=connections, current=current)


def _get_overview_data(
    findings: list, dbt_findings: list, table_rows: list[dict],
    state_db: BaseStateStore, conn_name: str,
) -> OverviewResponse:
    """Build overview response from loaded data."""
    stats = get_stats(findings, state_db, conn_name)
    findings_trend = get_findings_trend(state_db)
    prev = get_previous_stats(state_db)
    dbt_stats = get_dbt_stats(dbt_findings)

    findings_by_connection = get_findings_by_connection(findings)
    fbc = {
        conn: FindingsByConnection(errors=e, warnings=w)
        for conn, (e, w) in findings_by_connection.items()
    }

    top_tables = sorted(
        [r for r in table_rows if r["error_count"] > 0 or r["warning_count"] > 0],
        key=lambda r: (-r["error_count"], -r["warning_count"]),
    )[:5]

    prev_stats = (
        PrevStatsModel(error_count=prev[0], warning_count=prev[1]) if prev else None
    )

    disposition_counts = DispositionCounts(
        not_started=sum(1 for f in findings if f.disposition == "not_started"),
        in_progress=sum(1 for f in findings if f.disposition == "in_progress"),
        no_action=sum(1 for f in findings if f.disposition == "no_action"),
        completed=sum(1 for f in findings if f.disposition == "completed"),
    )

    return OverviewResponse(
        stats=DashboardStatsModel.model_validate(stats),
        dbt_stats=DbtStatsModel.model_validate(dbt_stats),
        findings_by_connection=fbc,
        findings_trend=[FindingsTrendPointModel.model_validate(p) for p in findings_trend],
        top_tables=[TableRowModel.from_dict(r) for r in top_tables],
        prev_stats=prev_stats,
        disposition_counts=disposition_counts,
    )


@router.get("/overview", response_model=OverviewResponse)
def api_overview(connection: str = Query("")):
    config = load_config()
    conn_name = _get_current_connection(connection, config)
    with _state_db(conn_name, config) as (state_db, resolved_conn):
        findings = load_findings_from_db(state_db)
        hydrate_dispositions(findings, state_db)
        dbt_findings = load_dbt_findings_from_db(state_db)
        findings_by_table_map = get_findings_by_table(findings)
        table_rows = _build_table_rows(state_db, resolved_conn, findings_by_table_map)
        return _get_overview_data(
            findings, dbt_findings, table_rows, state_db, resolved_conn,
        )


@router.get("/findings", response_model=FindingsResponse)
def api_findings(
    connection: str = Query(""),
    check_type: str = Query(""),
    severity: str = Query(""),
    schema: str = Query(""),
    disposition: str = Query(""),
    q: str = Query(""),
    page: int = Query(1, ge=1),
):
    config = load_config()
    conn_name = _get_current_connection(connection, config)
    with _state_db(conn_name, config) as (state_db, conn_name):
        findings = load_findings_from_db(state_db)
        hydrate_dispositions(findings, state_db)
        last_check_time = state_db.get_last_check_time()

    filtered = filter_findings(
        findings, check_type, severity, schema, connection, q, disposition,
    )
    stats = get_findings_stats(filtered)
    page_findings, total, total_pages = paginate(filtered, page)

    check_types = sorted({f.check_type for f in findings})
    severities = sorted({f.severity for f in findings})
    schemas = sorted({f.schema_name for f in findings})
    dispositions = sorted({f.disposition for f in findings})

    return FindingsResponse(
        findings=[FindingModel.model_validate(f) for f in page_findings],
        stats=FindingsStatsModel.model_validate(stats),
        filters=FiltersModel(
            check_types=check_types,
            severities=severities,
            schemas=schemas,
            dispositions=dispositions,
        ),
        page=page,
        total_pages=total_pages,
        total=total,
        last_check_time=last_check_time,
    )


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
) -> tuple[list[dict], int, int]:
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
            r[sort_key] is None if not reverse else r[sort_key] is not None,
            r[sort_key] or 0
            if sort_key in ("columns", "row_count")
            else (r[sort_key] or ""),
        ),
        reverse=reverse,
    )

    page_rows, total, total_pages = paginate(table_rows, page)
    return page_rows, total, total_pages


@router.get("/tables", response_model=TablesResponse)
def api_tables(
    connection: str = Query(""),
    search: str = Query(""),
    sort: str = Query("table"),
    order: str = Query("asc"),
    page: int = Query(1, ge=1),
):
    config = load_config()
    conn_name = _get_current_connection(connection, config)
    with _state_db(conn_name, config) as (state_db, conn_name):
        findings = load_findings_from_db(state_db)
        findings_by_table_map = get_findings_by_table(findings)
        table_rows = _build_table_rows(state_db, conn_name, findings_by_table_map)

    page_rows, total, total_pages = _filter_sort_paginate(
        table_rows, search, sort, order, page,
    )

    return TablesResponse(
        tables=[TableRowModel.from_dict(r) for r in page_rows],
        page=page,
        total_pages=total_pages,
        total=total,
    )


@router.get("/table/{schema}/{table}", response_model=TableDetailResponse)
def api_table_detail(schema: str, table: str, connection: str = Query("")):
    config = load_config()
    conn_name = _get_current_connection(connection, config)
    with _state_db(conn_name, config) as (state_db, conn_name):
        findings = load_findings_from_db(state_db)
        hydrate_dispositions(findings, state_db)
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
        cost_records = state_db.get_latest_cost(conn_name) or []

    # Contract status for this table
    contract_match = None
    contracts_data = get_contracts_page_data(findings, config)
    for c in contracts_data.contracts:
        if c.schema_name == schema and c.table_name == table:
            contract_match = c
            break

    # Integrity syncs involving this table
    integrity_data = get_integrity_page_data(findings, config)
    full_name = f"{schema}.{table}"
    matching_syncs = [
        s for s in integrity_data.syncs
        if full_name in s.source_table or full_name in s.target_table
    ]

    # Cost data for this table
    table_costs = [
        r for r in cost_records
        if r.schema_name == schema and r.table_name == table
    ]
    cost_data = None
    if table_costs:
        cost_data = TableCostModel(
            query_count=sum(r.query_count for r in table_costs),
            estimated_cost_usd=sum(r.estimated_cost_usd for r in table_costs),
            top_users=[
                CostUserModel(
                    user=r.user_email,
                    cost_usd=r.estimated_cost_usd,
                    queries=r.query_count,
                )
                for r in sorted(
                    table_costs, key=lambda x: -x.estimated_cost_usd,
                )
            ],
        )

    return TableDetailResponse(
        table_info=TableInfoModel.model_validate(table_info) if table_info else None,
        findings=[FindingModel.model_validate(f) for f in table_findings],
        volume_stats=VolumeStatsModel.model_validate(vol_stats),
        volume_timeseries=timeseries,
        history=TableHistoryModel.model_validate(history),
        schema_diff=SchemaDiffModel.model_validate(schema_diff) if schema_diff else None,
        contract=ContractStatusModel.model_validate(contract_match) if contract_match else None,
        integrity_syncs=[SyncStatusModel.model_validate(s) for s in matching_syncs],
        cost=cost_data,
    )


@router.get("/history", response_model=HistoryResponse)
def api_history(connection: str = Query(""), days: int = Query(30)):
    config = load_config()
    conn_name = _get_current_connection(connection, config)
    with _state_db(conn_name, config) as (state_db, conn_name):
        snapshots = get_snapshot_history(state_db, days, conn_name)

    return HistoryResponse(
        snapshots=[SnapshotInfoModel.model_validate(s) for s in snapshots],
        days=days,
    )


@router.get("/usage", response_model=UsageResponse)
def api_usage(connection: str = Query("")):
    config = load_config()
    conn_name = _get_current_connection(connection, config)
    with _state_db(conn_name, config) as (state_db, conn_name):
        findings = load_findings_from_db(state_db)
        cost_daily = get_cost_daily_timeseries(
            state_db, days=30, connection_name=conn_name
        )
        least_used = get_least_used_tables(state_db, conn_name)
        cost_summary = build_cost_summary(state_db, conn_name)

    usage_findings = get_usage_findings(findings)
    stats = get_usage_stats(usage_findings, cost_summary)

    return UsageResponse(
        stats=UsageStatsModel.model_validate(stats),
        usage_findings=[FindingModel.model_validate(f) for f in usage_findings],
        cost_summary=cost_summary,
        cost_daily=cost_daily,
        least_used=[LeastUsedTableModel.model_validate(t) for t in least_used],
    )


@router.get("/dbt", response_model=DbtResponse)
def api_dbt(connection: str = Query("")):
    config = load_config()
    conn_name = _get_current_connection(connection, config)
    with _state_db(conn_name, config) as (state_db, _conn):
        dbt_findings = load_dbt_findings_from_db(state_db)
        leaderboard = get_dbt_execution_leaderboard(dbt_findings)
        run_history = get_dbt_run_history(state_db)

    dbt_stats = get_dbt_stats(dbt_findings)
    resource_types = sorted({f.resource_type for f in dbt_findings})
    severities = sorted({f.severity for f in dbt_findings})

    return DbtResponse(
        dbt_stats=DbtStatsModel.model_validate(dbt_stats),
        dbt_findings=[DbtFindingModel.model_validate(f) for f in dbt_findings],
        resource_types=resource_types,
        severities=severities,
        execution_leaderboard=[
            DbtExecutionLeaderboardModel.model_validate(e) for e in leaderboard
        ],
        run_history=[
            DbtRunHistoryPointModel.model_validate(p) for p in run_history
        ],
    )


@router.get("/dbt/node/{unique_id:path}/previous-sql")
def api_dbt_previous_sql(
    unique_id: str,
    dbt_run_id: int | None = Query(None),
    connection: str = Query(""),
):
    with _state_db(connection) as (state_db, _conn):
        prev_sql = state_db.get_previous_compiled_code(unique_id, dbt_run_id)
    return {"unique_id": unique_id, "previous_sql": prev_sql}


@router.get("/dbt/node/{unique_id:path}/timings", response_model=DbtNodeTimingsResponse)
def api_dbt_node_timings(unique_id: str, connection: str = Query("")):
    config = load_config()
    conn_name = _get_current_connection(connection, config)
    with _state_db(conn_name, config) as (state_db, _conn):
        timings = get_dbt_node_timeseries(state_db, unique_id)

    return DbtNodeTimingsResponse(
        unique_id=unique_id,
        timings=[DbtNodeTimingModel(**t) for t in timings],
    )


@router.get("/contracts", response_model=ContractsResponse)
def api_contracts(connection: str = Query("")):
    config = load_config()
    conn_name = _get_current_connection(connection, config)
    with _state_db(conn_name, config) as (state_db, _conn):
        findings = load_findings_from_db(state_db)
        last_check_time = state_db.get_last_check_time()

    page_data = get_contracts_page_data(findings, config)
    return ContractsResponse(
        contracts=[ContractStatusModel.model_validate(c) for c in page_data.contracts],
        pass_count=page_data.pass_count,
        fail_count=page_data.fail_count,
        total_count=page_data.total_count,
        configured=page_data.configured,
        last_check_time=last_check_time,
    )


@router.get("/integrity", response_model=IntegrityResponse)
def api_integrity(connection: str = Query("")):
    config = load_config()
    conn_name = _get_current_connection(connection, config)
    with _state_db(conn_name, config) as (state_db, _conn):
        findings = load_findings_from_db(state_db)
        last_check_time = state_db.get_last_check_time()

    page_data = get_integrity_page_data(findings, config)
    return IntegrityResponse(
        syncs=[SyncStatusModel.model_validate(s) for s in page_data.syncs],
        pass_count=page_data.pass_count,
        fail_count=page_data.fail_count,
        total_count=page_data.total_count,
        configured=page_data.configured,
        last_check_time=last_check_time,
    )


class DispositionRequest(BaseModel):
    disposition: str
    comment: str = ""


class BulkDispositionRequest(BaseModel):
    finding_ids: list[int]
    disposition: str
    comment: str = ""


def _validate_disposition(value: str) -> JSONResponse | None:
    """Return a 400 response if the disposition is invalid, else None."""
    from olly.models import Disposition

    valid = {d.value for d in Disposition}
    if value not in valid:
        return JSONResponse(
            {"error": f"Invalid disposition, must be one of {sorted(valid)}"},
            status_code=400,
        )
    return None


@router.put("/findings/bulk-disposition")
def api_bulk_disposition(body: BulkDispositionRequest):
    if error := _validate_disposition(body.disposition):
        return error
    if not body.finding_ids:
        return {"success": True, "count": 0}
    with _state_db() as (state_db, _conn):
        for fid in body.finding_ids:
            state_db.set_disposition(fid, body.disposition, body.comment)
    return {"success": True, "count": len(body.finding_ids)}


@router.put("/findings/{finding_id}/disposition")
def api_set_disposition(finding_id: int, body: DispositionRequest):
    if error := _validate_disposition(body.disposition):
        return error
    with _state_db() as (state_db, _conn):
        disposition_id = state_db.set_disposition(
            finding_id, body.disposition, body.comment,
        )
    return {"success": True, "disposition_id": disposition_id}


@router.get("/findings/{finding_id}/dispositions", response_model=DispositionHistoryResponse)
def api_disposition_history(finding_id: int):
    with _state_db() as (state_db, _conn):
        history = state_db.get_disposition_history(finding_id)
        current_map = state_db.get_current_dispositions([finding_id])
    current = current_map.get(finding_id, "not_started")
    return DispositionHistoryResponse(
        finding_id=finding_id,
        current_disposition=current,
        history=history,
    )


@router.post("/refresh")
def api_refresh():
    from olly.cli.check import run_checks
    from olly.config import load_config as _load_config
    from olly.results import write_findings_json

    config = _load_config()
    try:
        findings, dbt_findings, cost_records = run_checks(config)
    except Exception as exc:
        return JSONResponse(
            {"error": f"Check run failed: {exc}"}, status_code=500,
        )
    write_findings_json(findings, dbt_findings=dbt_findings, cost_records=cost_records)

    return JSONResponse({"success": True})
