from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from olly.dashboard.data import (
    filter_findings,
    get_critical_findings,
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
    load_findings,
)
from olly.models import ColumnInfo, CostRecord, Finding, TableInfo, VolumeRecord
from olly.results import write_findings_json
from olly.state import StateDB, get_olly_dir


# ── data.py tests ──


def test_load_findings_no_file(tmp_path):
    findings, generated_at = load_findings(tmp_path / "nope.json")
    assert findings == []
    assert generated_at is None


def test_load_findings_roundtrip(tmp_path):
    path = tmp_path / "findings.json"
    original = [
        Finding("schema", "error", "main", "orders", "Column added"),
        Finding("volume", "warning", "main", "customers", "Z-score high"),
    ]
    write_findings_json(original, path)
    loaded, generated_at = load_findings(path)
    assert len(loaded) == 2
    assert loaded[0].check_type == "schema"
    assert loaded[1].severity == "warning"
    assert generated_at is not None
    # connection_name defaults to "" and survives roundtrip
    assert loaded[0].connection_name == ""
    assert loaded[1].connection_name == ""


def test_load_findings_roundtrip_with_connection_name(tmp_path):
    """Findings with explicit connection_name survive JSON roundtrip."""
    path = tmp_path / "findings.json"
    original = [
        Finding(
            "schema", "error", "main", "orders", "Column added",
            connection_name="warehouse_a",
        ),
        Finding(
            "volume", "warning", "main", "customers", "Z-score high",
            connection_name="warehouse_b",
        ),
    ]
    write_findings_json(original, path)
    loaded, generated_at = load_findings(path)
    assert len(loaded) == 2
    assert loaded[0].connection_name == "warehouse_a"
    assert loaded[1].connection_name == "warehouse_b"
    assert generated_at is not None


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

    # Snapshot 1: id, name
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

    # Snapshot 2: id (type changed), status (added), name removed
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


# ── API routes tests ──


@pytest.fixture
def dashboard_client(tmp_path, monkeypatch):
    """TestClient with findings and state in tmp_path."""
    # Set up state DB
    state_db_path = get_olly_dir(tmp_path) / "state.db"
    state_db_path.parent.mkdir(parents=True)
    state_db = StateDB(db_path=state_db_path)
    state_db.init_db()

    snap_id = state_db.create_snapshot()
    state_db.store_schema_data(
        snap_id,
        [
            TableInfo(
                "main",
                "orders",
                "TABLE",
                [
                    ColumnInfo("id", "INTEGER", False),
                    ColumnInfo("amount", "DOUBLE", False),
                ],
            ),
        ],
    )
    state_db.store_volume_data(snap_id, [VolumeRecord("main", "orders", 100)])

    # Store findings in state DB (dashboard now reads from here)
    test_findings = [
        Finding("schema", "error", "main", "orders", "Column added: amount"),
        Finding("volume", "warning", "main", "orders", "Z-score 3.5"),
    ]
    state_db.store_findings(test_findings)
    state_db.close()

    # Write findings JSON (kept as optional CLI artifact)
    findings_path = get_olly_dir(tmp_path) / "findings.json"
    write_findings_json(test_findings, findings_path)

    # Monkeypatch paths and _state_db to use tmp_path state.
    from olly.state import get_olly_dir as original_get_olly_dir
    test_olly_dir = original_get_olly_dir(tmp_path)

    def mock_get_olly_dir(project_root=None):
        return test_olly_dir

    monkeypatch.setattr("olly.state.get_olly_dir", mock_get_olly_dir)
    monkeypatch.setattr("olly.results.get_olly_dir", mock_get_olly_dir)

    @contextmanager
    def mock_state_db(connection_name: str = ""):
        yield StateDB(db_path=state_db_path), ""

    def mock_get_current_connection(connection_param: str = ""):
        return "test_connection"

    def mock_get_all_connections():
        return ["test_connection"]

    monkeypatch.setattr("olly.dashboard.api_routes._state_db", mock_state_db)
    monkeypatch.setattr("olly.dashboard.api_routes._get_current_connection", mock_get_current_connection)
    monkeypatch.setattr("olly.dashboard.api_routes._get_all_connections", mock_get_all_connections)
    monkeypatch.setattr("olly.dashboard.data.get_all_connections", mock_get_all_connections)

    from olly.dashboard.app import app

    return TestClient(app)


def test_api_overview(dashboard_client):
    resp = dashboard_client.get("/api/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["stats"]["error_count"] == 1
    assert data["stats"]["warning_count"] == 1
    assert "top_tables" in data
    assert "findings_trend" in data
    assert isinstance(data["findings_by_connection"], dict)


def test_api_findings_no_filter(dashboard_client):
    resp = dashboard_client.get("/api/findings")
    assert resp.status_code == 200
    data = resp.json()
    assert "orders" in str(data["findings"])


def test_api_findings_filter_check_type(dashboard_client):
    resp = dashboard_client.get("/api/findings?check_type=schema")
    assert resp.status_code == 200
    data = resp.json()
    assert all(f["check_type"] == "schema" for f in data["findings"])


def test_api_findings_filter_severity(dashboard_client):
    resp = dashboard_client.get("/api/findings?severity=warning")
    assert resp.status_code == 200
    data = resp.json()
    assert all(f["severity"] == "warning" for f in data["findings"])


def test_api_table_detail(dashboard_client):
    resp = dashboard_client.get("/api/table/main/orders")
    assert resp.status_code == 200
    data = resp.json()
    assert data["table_info"]["table_name"] == "orders"
    assert data["volume_stats"]["current"] == 100


def test_api_tables(dashboard_client):
    resp = dashboard_client.get("/api/tables")
    assert resp.status_code == 200
    data = resp.json()
    assert any(t["table"] == "orders" for t in data["tables"])
    assert data["total"] >= 1


def test_api_tables_search(dashboard_client):
    resp = dashboard_client.get("/api/tables?search=orders")
    assert resp.status_code == 200
    data = resp.json()
    assert any(t["table"] == "orders" for t in data["tables"])


def test_api_tables_search_no_match(dashboard_client):
    resp = dashboard_client.get("/api/tables?search=zzzzz")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tables"]) == 0


def test_api_tables_sort(dashboard_client):
    resp = dashboard_client.get("/api/tables?sort=row_count&order=desc")
    assert resp.status_code == 200
    data = resp.json()
    assert any(t["table"] == "orders" for t in data["tables"])


def test_api_table_detail_not_found_graceful(dashboard_client):
    resp = dashboard_client.get("/api/table/main/nonexistent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["table_info"] is None


def test_api_history(dashboard_client):
    resp = dashboard_client.get("/api/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["days"] == 30


def test_api_connections(dashboard_client):
    resp = dashboard_client.get("/api/connections")
    assert resp.status_code == 200
    data = resp.json()
    assert "test_connection" in data["connections"]


def test_api_dbt(dashboard_client):
    resp = dashboard_client.get("/api/dbt")
    assert resp.status_code == 200
    data = resp.json()
    assert "dbt_stats" in data
    assert "dbt_findings" in data


# ── usage page tests ──


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
    assert stats.by_connection["default"] == (1, 0)  # schema finding has no connection_name
    assert stats.by_connection["conn1"] == (0, 1)
    assert stats.by_connection["conn2"] == (1, 0)


def test_filter_findings():
    findings = [
        Finding("schema", "error", "main", "orders", "Column added"),
        Finding("volume", "warning", "main", "customers", "Z-score high"),
        Finding("schema", "error", "staging", "products", "Column removed", connection_name="conn1"),
    ]

    # Filter by check_type
    schema_findings = filter_findings(findings, check_type="schema")
    assert len(schema_findings) == 2

    # Filter by severity
    errors = filter_findings(findings, severity="error")
    assert len(errors) == 2

    # Filter by schema_name
    main_findings = filter_findings(findings, schema_name="main")
    assert len(main_findings) == 2

    # Filter by connection
    conn1_findings = filter_findings(findings, connection="conn1")
    assert len(conn1_findings) == 1

    # Filter by query
    query_findings = filter_findings(findings, q="column")
    assert len(query_findings) == 2


def test_get_findings_by_connection():
    findings = [
        Finding("schema", "error", "main", "orders", "desc", connection_name="conn1"),
        Finding("volume", "warning", "main", "customers", "desc", connection_name="conn1"),
        Finding("volume", "error", "main", "products", "desc", connection_name="conn2"),
        Finding("schema", "warning", "main", "users", "desc"),  # No connection_name
    ]
    by_conn = get_findings_by_connection(findings)
    assert by_conn["conn1"] == (1, 1)
    assert by_conn["conn2"] == (1, 0)
    assert by_conn["default"] == (0, 1)


def test_get_critical_findings():
    findings = [
        Finding("freshness", "error", "main", "orders", "stale"),
        Finding("volume", "error", "main", "customers", "spike"),
        Finding("schema", "error", "main", "products", "changed"),
        Finding("volume", "warning", "main", "users", "anomaly"),
        Finding("integrity", "error", "main", "events", "mismatch"),
    ]
    critical = get_critical_findings(findings, limit=2)
    assert len(critical) == 2
    # Should prioritize by type: volume > schema > freshness > integrity
    assert critical[0].check_type == "volume"
    assert critical[1].check_type == "schema"


def test_get_findings_by_table():
    findings = [
        Finding("schema", "error", "main", "orders", "desc"),
        Finding("volume", "warning", "main", "orders", "desc"),
        Finding("volume", "error", "main", "customers", "desc"),
    ]
    by_table = get_findings_by_table(findings)
    assert by_table[("main", "orders")] == (1, 1)
    assert by_table[("main", "customers")] == (1, 0)


def test_api_usage_empty(dashboard_client):
    resp = dashboard_client.get("/api/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert "stats" in data
    assert data["stats"]["unused_count"] == 0


def test_api_usage_with_findings(tmp_path, monkeypatch):
    """Usage API with usage findings and cost data."""
    state_db_path = get_olly_dir(tmp_path) / "state.db"
    state_db_path.parent.mkdir(parents=True)
    state_db = StateDB(db_path=state_db_path)
    state_db.init_db()

    usage_findings = [
        Finding(
            "usage",
            "error",
            "main",
            "old_table",
            "Unused table",
            details={"last_queried_at": None, "lookback_days": 90},
        ),
        Finding(
            "usage",
            "warning",
            "main",
            "stale_table",
            "Stale table",
            details={"last_queried_at": "2025-06-01T00:00:00", "days_unused": 45.0},
        ),
    ]
    state_db.store_findings(usage_findings)
    state_db.close()

    findings_path = get_olly_dir(tmp_path) / "findings.json"
    cost_records = [
        CostRecord("main", "orders", "alice@co.com", 5000000, 25.00, 10),
        CostRecord("main", "users", "bob@co.com", 2000000, 8.50, 3),
    ]
    write_findings_json(
        usage_findings,
        findings_path,
        cost_records=cost_records,
    )

    from olly.state import get_olly_dir as original_get_olly_dir
    test_olly_dir = original_get_olly_dir(tmp_path)

    def mock_get_olly_dir(project_root=None):
        return test_olly_dir

    monkeypatch.setattr("olly.state.get_olly_dir", mock_get_olly_dir)
    monkeypatch.setattr("olly.results.get_olly_dir", mock_get_olly_dir)

    @contextmanager
    def mock_state_db(connection_name: str = ""):
        yield StateDB(db_path=state_db_path), ""

    def mock_get_current_connection(connection_param: str = ""):
        return "test_connection"

    def mock_get_all_connections():
        return ["test_connection"]

    monkeypatch.setattr("olly.dashboard.api_routes._state_db", mock_state_db)
    monkeypatch.setattr("olly.dashboard.api_routes._get_current_connection", mock_get_current_connection)
    monkeypatch.setattr("olly.dashboard.api_routes._get_all_connections", mock_get_all_connections)
    monkeypatch.setattr("olly.dashboard.data.get_all_connections", mock_get_all_connections)

    from olly.dashboard.app import app

    client = TestClient(app)
    resp = client.get("/api/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["stats"]["unused_count"] == 1
    assert data["stats"]["stale_count"] == 1
    assert data["cost_summary"]["total_cost_usd"] == 33.50
    assert any("alice@co.com" in u["user"] for u in data["cost_summary"]["top_users"])
