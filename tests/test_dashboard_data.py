from __future__ import annotations

import pytest

from olly.dashboard.data import (
    filter_findings,
    get_findings_by_connection,
    get_findings_by_table,
    get_findings_stats,
    get_schema_diff,
    get_stats,
    get_table_history,
    get_table_info,
    get_usage_findings,
    get_usage_stats,
    get_volume_stats,
    get_volume_timeseries,
    load_cost_summary,
)
from olly.models import ColumnInfo, CostRecord, Finding, TableInfo, VolumeRecord
from olly.results import write_findings_json
from olly.state import StateDB


def test_get_stats(tmp_path):
    state_db = StateDB(db_path=tmp_path / "state.db")
    state_db.init_db()

    snap_id = state_db.create_snapshot()
    state_db.store_schema_data(
        snap_id,
        [
            TableInfo("main", "orders", "TABLE", [ColumnInfo("id", "INTEGER", False)]),
            TableInfo(
                "main", "customers", "TABLE", [ColumnInfo("id", "INTEGER", False)]
            ),
        ],
    )

    findings = [
        Finding("schema", "error", "main", "orders", "desc"),
        Finding("volume", "warning", "main", "customers", "desc"),
        Finding("volume", "error", "main", "customers", "desc2"),
    ]
    state_db.store_findings(findings)
    stats = get_stats(findings, state_db)
    last_check_time = stats.last_check_time
    state_db.close()

    assert stats.error_count == 2
    assert stats.warning_count == 1
    assert stats.tables_monitored == 2
    assert last_check_time is not None


def test_get_volume_timeseries(tmp_path):
    state_db = StateDB(db_path=tmp_path / "state.db")
    state_db.init_db()

    for count in [100, 110, 120]:
        snap_id = state_db.create_snapshot()
        state_db.store_volume_data(snap_id, [VolumeRecord("main", "orders", count)])

    ts = get_volume_timeseries(state_db, "main", "orders")
    state_db.close()

    assert len(ts) == 3
    assert ts[0]["row_count"] == 100
    assert ts[2]["row_count"] == 120
    assert "snapshot" in ts[0]


def test_get_table_info(tmp_path):
    state_db = StateDB(db_path=tmp_path / "state.db")
    state_db.init_db()

    snap_id = state_db.create_snapshot()
    state_db.store_schema_data(
        snap_id,
        [TableInfo("main", "orders", "TABLE", [ColumnInfo("id", "INTEGER", False)])],
    )

    info = get_table_info(state_db, "main", "orders")
    assert info is not None
    assert info.table_name == "orders"

    missing = get_table_info(state_db, "main", "nope")
    assert missing is None
    state_db.close()


def test_get_volume_stats(tmp_path):
    state_db = StateDB(db_path=tmp_path / "state.db")
    state_db.init_db()

    for count in [100, 110, 120]:
        snap_id = state_db.create_snapshot()
        state_db.store_volume_data(snap_id, [VolumeRecord("main", "orders", count)])

    vs = get_volume_stats(state_db, "main", "orders")
    state_db.close()

    assert vs.current == 120
    assert vs.previous == 110
    assert vs.delta == 10
    assert vs.delta_pct == pytest.approx(9.1, abs=0.1)
    assert vs.minimum == 100
    assert vs.maximum == 120
    assert vs.average == pytest.approx(110.0)
    assert vs.snapshot_count == 3


def test_get_volume_stats_empty(tmp_path):
    state_db = StateDB(db_path=tmp_path / "state.db")
    state_db.init_db()
    vs = get_volume_stats(state_db, "main", "orders")
    state_db.close()
    assert vs.current is None
    assert vs.snapshot_count == 0


def test_get_table_history(tmp_path):
    state_db = StateDB(db_path=tmp_path / "state.db")
    state_db.init_db()

    for _ in range(3):
        snap_id = state_db.create_snapshot()
        state_db.store_schema_data(
            snap_id,
            [
                TableInfo(
                    "main", "orders", "TABLE", [ColumnInfo("id", "INTEGER", False)]
                )
            ],
        )

    h = get_table_history(state_db, "main", "orders")
    state_db.close()

    assert h.snapshot_count == 3
    assert h.first_seen is not None


def test_get_schema_diff(tmp_path):
    state_db = StateDB(db_path=tmp_path / "state.db")
    state_db.init_db()

    snap1 = state_db.create_snapshot()
    state_db.store_schema_data(
        snap1,
        [
            TableInfo(
                "main",
                "orders",
                "TABLE",
                [
                    ColumnInfo("id", "INTEGER", False),
                    ColumnInfo("name", "VARCHAR", False),
                ],
            ),
        ],
    )

    snap2 = state_db.create_snapshot()
    state_db.store_schema_data(
        snap2,
        [
            TableInfo(
                "main",
                "orders",
                "TABLE",
                [
                    ColumnInfo("id", "BIGINT", False),
                    ColumnInfo("status", "VARCHAR", True),
                ],
            ),
        ],
    )

    diff = get_schema_diff(state_db, "main", "orders")
    state_db.close()

    assert diff is not None
    assert len(diff.added) == 1
    assert diff.added[0].column_name == "status"
    assert len(diff.removed) == 1
    assert diff.removed[0].column_name == "name"
    assert len(diff.type_changes) == 1
    assert diff.type_changes[0] == ("id", "INTEGER", "BIGINT")


def test_get_schema_diff_no_changes(tmp_path):
    state_db = StateDB(db_path=tmp_path / "state.db")
    state_db.init_db()

    cols = [ColumnInfo("id", "INTEGER", False)]
    for _ in range(2):
        snap_id = state_db.create_snapshot()
        state_db.store_schema_data(
            snap_id,
            [
                TableInfo("main", "orders", "TABLE", cols),
            ],
        )

    diff = get_schema_diff(state_db, "main", "orders")
    state_db.close()
    assert diff is None


def test_get_schema_diff_single_snapshot(tmp_path):
    state_db = StateDB(db_path=tmp_path / "state.db")
    state_db.init_db()

    snap_id = state_db.create_snapshot()
    state_db.store_schema_data(
        snap_id,
        [
            TableInfo("main", "orders", "TABLE", [ColumnInfo("id", "INTEGER", False)]),
        ],
    )

    diff = get_schema_diff(state_db, "main", "orders")
    state_db.close()
    assert diff is None


def test_get_usage_findings():
    findings = [
        Finding("schema", "error", "main", "orders", "Column added"),
        Finding(
            "usage",
            "warning",
            "main",
            "stale_tbl",
            "Stale table",
            details={"last_queried_at": "2025-01-01T00:00:00", "days_unused": 45.0},
        ),
        Finding(
            "usage",
            "error",
            "main",
            "unused_tbl",
            "Unused table",
            details={"last_queried_at": None},
        ),
    ]
    result = get_usage_findings(findings)
    assert len(result) == 2
    assert result[0].severity == "error"
    assert result[1].severity == "warning"


def test_get_usage_stats():
    usage_findings = [
        Finding("usage", "error", "main", "t1", "Unused"),
        Finding("usage", "error", "main", "t2", "Unused"),
        Finding("usage", "warning", "main", "t3", "Stale"),
    ]
    cost_summary = {"total_cost_usd": 42.50}
    stats = get_usage_stats(usage_findings, cost_summary)
    assert stats.unused_count == 2
    assert stats.stale_count == 1
    assert stats.total_cost_usd == 42.50

    stats_no_cost = get_usage_stats(usage_findings, None)
    assert stats_no_cost.total_cost_usd is None


def test_load_cost_summary(tmp_path):
    path = tmp_path / "findings.json"
    cost_records = [
        CostRecord("main", "orders", "user@test.com", 1000000, 10.50, 5),
    ]
    write_findings_json([], path, cost_records=cost_records)
    summary = load_cost_summary(path)
    assert summary is not None
    assert summary["total_cost_usd"] == 10.50
    assert len(summary["top_tables"]) == 1


def test_load_cost_summary_missing(tmp_path):
    path = tmp_path / "findings.json"
    write_findings_json([], path)
    summary = load_cost_summary(path)
    assert summary is None


def test_get_findings_stats():
    findings = [
        Finding("schema", "error", "main", "orders", "desc"),
        Finding("volume", "warning", "main", "customers", "desc", connection_name="conn1"),
        Finding("volume", "error", "main", "customers", "desc2", connection_name="conn2"),
    ]
    stats = get_findings_stats(findings)
    assert stats.total_count == 3
    assert stats.error_count == 2
    assert stats.warning_count == 1
    assert stats.by_check_type["schema"] == (1, 0)
    assert stats.by_check_type["volume"] == (1, 1)
    assert stats.by_connection["default"] == (1, 0)
    assert stats.by_connection["conn1"] == (0, 1)
    assert stats.by_connection["conn2"] == (1, 0)


def test_filter_findings():
    findings = [
        Finding("schema", "error", "main", "orders", "Column added"),
        Finding("volume", "warning", "main", "customers", "Z-score high"),
        Finding("schema", "error", "staging", "products", "Column removed", connection_name="conn1"),
    ]

    schema_findings = filter_findings(findings, check_type="schema")
    assert len(schema_findings) == 2

    errors = filter_findings(findings, severity="error")
    assert len(errors) == 2

    main_findings = filter_findings(findings, schema_name="main")
    assert len(main_findings) == 2

    conn1_findings = filter_findings(findings, connection="conn1")
    assert len(conn1_findings) == 1

    query_findings = filter_findings(findings, q="column")
    assert len(query_findings) == 2


def test_get_findings_by_connection():
    findings = [
        Finding("schema", "error", "main", "orders", "desc", connection_name="conn1"),
        Finding("volume", "warning", "main", "customers", "desc", connection_name="conn1"),
        Finding("volume", "error", "main", "products", "desc", connection_name="conn2"),
        Finding("schema", "warning", "main", "users", "desc"),
    ]
    by_conn = get_findings_by_connection(findings)
    assert by_conn["conn1"] == (1, 1)
    assert by_conn["conn2"] == (1, 0)
    assert by_conn["default"] == (0, 1)


def test_get_findings_by_table():
    findings = [
        Finding("schema", "error", "main", "orders", "desc"),
        Finding("volume", "warning", "main", "orders", "desc"),
        Finding("volume", "error", "main", "customers", "desc"),
    ]
    by_table = get_findings_by_table(findings)
    assert by_table[("main", "orders")] == (1, 1)
    assert by_table[("main", "customers")] == (1, 0)
