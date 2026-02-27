from olly.config import ConnectionConfig, NamedConnection, OllyConfig, Selection
from olly.models import ColumnInfo, CostRecord, DbtFinding, Finding, TableInfo, VolumeRecord
from olly.state import StateDB, open_state


def test_create_and_retrieve_snapshot(state_db):
    tables = [
        TableInfo(
            schema_name="main",
            table_name="orders",
            table_type="TABLE",
            columns=[
                ColumnInfo("id", "int32", False),
                ColumnInfo("amount", "float64", False),
            ],
        ),
    ]
    volumes = [VolumeRecord("main", "orders", 100)]

    sid = state_db.create_snapshot()
    state_db.store_schema_data(sid, tables)
    state_db.store_volume_data(sid, volumes)

    schema = state_db.get_latest_schema()
    assert len(schema) == 1
    assert schema[0].table_name == "orders"
    assert len(schema[0].columns) == 2

    vols = state_db.get_latest_volume()
    assert len(vols) == 1
    assert vols[0].row_count == 100


def test_volume_history(state_db):
    counts = [100, 105, 102, 98, 110]
    for count in counts:
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [VolumeRecord("main", "orders", count)])

    history = state_db.get_volume_history("main", "orders", 10)
    # Most recent first
    assert history == list(reversed(counts))


def test_prune_old_snapshots(state_db):
    for i in range(10):
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [VolumeRecord("main", "t", i)])

    state_db.prune_old_snapshots(keep=3)

    history = state_db.get_volume_history("main", "t", 100)
    assert len(history) == 3
    assert history == [9, 8, 7]


def test_has_snapshots_empty(state_db):
    assert not state_db.has_snapshots()


def test_has_snapshots_after_insert(state_db):
    state_db.create_snapshot()
    assert state_db.has_snapshots()


def test_unchanged_count(state_db):
    # 5 snapshots all with count=100
    for _ in range(5):
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [VolumeRecord("main", "t", 100)])

    assert state_db.get_recent_volume_unchanged_count("main", "t", 10) == 5


def test_unchanged_count_with_change(state_db):
    for count in [100, 100, 100, 200]:
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [VolumeRecord("main", "t", count)])

    # Most recent is 200, so only 1 consecutive
    assert state_db.get_recent_volume_unchanged_count("main", "t", 10) == 1


def test_context_manager(tmp_path):
    """StateDB closes connection when used as a context manager."""
    db_path = tmp_path / "ctx.db"
    with StateDB(db_path=db_path) as db:
        db.init_db()
        db.create_snapshot()
        assert db.has_snapshots()
    # Connection is closed after exiting the with block — verify by
    # opening a fresh connection and checking the data persisted.
    with StateDB(db_path=db_path) as db:
        db.init_db()
        assert db.has_snapshots()


def test_init_db_creates_tables(tmp_path):
    """Fresh database gets all tables created."""
    db_path = tmp_path / "v.db"
    with StateDB(db_path=db_path) as db:
        db.init_db()
        tables = {
            r[0]
            for r in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "snapshots" in tables
        assert "schema_snapshot" in tables
        assert "volume_snapshot" in tables
        assert "cost_runs" in tables
        assert "cost_records" in tables
        assert "findings" in tables
        assert "dbt_findings" in tables


def test_init_db_idempotent(tmp_path):
    """Calling init_db twice doesn't error."""
    db_path = tmp_path / "idem.db"
    with StateDB(db_path=db_path) as db:
        db.init_db()
        db.init_db()
        assert db.conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 0


def test_auto_init_on_construction(tmp_path):
    """Tables are created automatically without calling init_db."""
    db_path = tmp_path / "auto.db"
    with StateDB(db_path=db_path) as db:
        sid = db.create_snapshot()
        assert sid == 1
        assert db.has_snapshots()


def test_indexes_created(tmp_path):
    """Indexes on snapshot_id are created for each child table."""
    db_path = tmp_path / "idx.db"
    with StateDB(db_path=db_path) as db:
        indexes = {
            r[0]
            for r in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_schema_snapshot_sid" in indexes
        assert "idx_volume_snapshot_sid" in indexes
        assert "idx_cost_records_run_id" in indexes
        assert "idx_findings_created_at" in indexes
        assert "idx_findings_connection" in indexes
        assert "idx_dbt_findings_created_at" in indexes


def test_get_latest_cost(state_db):
    """get_latest_cost returns cost records from the most recent run."""
    record = CostRecord(
        schema_name="main",
        table_name="orders",
        user_email="user@example.com",
        total_bytes_billed=1_000_000,
        estimated_cost_usd=5.0,
        query_count=3,
    )
    state_db.store_cost_data([record])

    latest = state_db.get_latest_cost()
    assert len(latest) == 1
    assert latest[0].estimated_cost_usd == 5.0
    assert latest[0].table_name == "orders"


def test_get_latest_cost_empty(state_db):
    """get_latest_cost returns empty list when no cost runs exist."""
    assert state_db.get_latest_cost() == []


def test_open_state_returns_sqlite_by_default():
    """open_state returns a StateDB when state_schema is not set."""
    nc = NamedConnection(
        name="primary",
        connection=ConnectionConfig(type="duckdb", path="x.duckdb"),
        selection=Selection(),
    )
    config = OllyConfig(connections={"primary": nc})
    store = open_state(config)
    assert isinstance(store, StateDB)
    store.close()


def test_store_and_retrieve_findings(state_db):
    """store_findings persists findings and get_findings_history retrieves them."""
    findings = [
        Finding(
            check_type="schema",
            severity="error",
            schema_name="main",
            table_name="orders",
            description="Column removed",
            details={"column": "status"},
            connection_name="primary",
        ),
        Finding(
            check_type="volume",
            severity="warning",
            schema_name="main",
            table_name="users",
            description="Volume anomaly detected",
            details={"z_score": 3.2},
            connection_name="primary",
        ),
    ]
    state_db.store_findings(findings)

    history = state_db.get_findings_history(limit=10)
    assert len(history) == 2
    # Most recent first (reversed order from insertion)
    assert history[0].check_type == "volume"
    assert history[0].severity == "warning"
    assert history[0].table_name == "users"
    assert history[0].details["z_score"] == 3.2
    assert history[1].check_type == "schema"
    assert history[1].severity == "error"
    assert history[1].table_name == "orders"


def test_store_empty_findings(state_db):
    """store_findings handles empty list gracefully."""
    state_db.store_findings([])
    history = state_db.get_findings_history()
    assert history == []


def test_get_findings_history_with_connection_filter(state_db):
    """get_findings_history can filter by connection name."""
    findings = [
        Finding(
            check_type="schema",
            severity="error",
            schema_name="main",
            table_name="t1",
            description="Issue 1",
            connection_name="conn1",
        ),
        Finding(
            check_type="schema",
            severity="error",
            schema_name="main",
            table_name="t2",
            description="Issue 2",
            connection_name="conn2",
        ),
    ]
    state_db.store_findings(findings)

    conn1_findings = state_db.get_findings_history(connection_name="conn1")
    assert len(conn1_findings) == 1
    assert conn1_findings[0].table_name == "t1"

    conn2_findings = state_db.get_findings_history(connection_name="conn2")
    assert len(conn2_findings) == 1
    assert conn2_findings[0].table_name == "t2"


def test_store_and_retrieve_dbt_findings(state_db):
    """store_dbt_findings persists dbt findings and get_dbt_findings_history retrieves them."""
    dbt_findings = [
        DbtFinding(
            resource_type="model",
            severity="error",
            unique_id="model.project.orders",
            status="error",
            execution_time=1.23,
            description="Model failed",
            details={"error": "SQL syntax error"},
        ),
        DbtFinding(
            resource_type="test",
            severity="warning",
            unique_id="test.project.check_nulls",
            status="warn",
            execution_time=0.5,
            description="Test warned",
            details={"rows_failed": 3},
        ),
    ]
    state_db.store_dbt_findings(dbt_findings)

    history = state_db.get_dbt_findings_history(limit=10)
    assert len(history) == 2
    # Most recent first
    assert history[0].resource_type == "test"
    assert history[0].status == "warn"
    assert history[0].details["rows_failed"] == 3
    assert history[1].resource_type == "model"
    assert history[1].execution_time == 1.23


def test_store_empty_dbt_findings(state_db):
    """store_dbt_findings handles empty list gracefully."""
    state_db.store_dbt_findings([])
    history = state_db.get_dbt_findings_history()
    assert history == []


def test_clean_deletes_sqlite_db(tmp_path):
    """clean() removes the SQLite database file."""
    db_path = tmp_path / "clean_test.db"
    db = StateDB(db_path=db_path)
    db.create_snapshot()
    assert db_path.exists()
    db.clean()
    assert not db_path.exists()


def test_clean_no_error_when_missing(tmp_path):
    """clean() is a no-op if the database file was already removed."""
    db_path = tmp_path / "already_gone.db"
    db = StateDB(db_path=db_path)
    db_path.unlink()
    db.close()
    db.clean()  # should not raise


def test_findings_tables_created(tmp_path):
    """Findings tables are created during initialization."""
    db_path = tmp_path / "findings.db"
    with StateDB(db_path=db_path) as db:
        tables = {
            r[0]
            for r in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "findings" in tables
        assert "dbt_findings" in tables


def test_findings_indexes_created(tmp_path):
    """Indexes for findings tables are created."""
    db_path = tmp_path / "findings_idx.db"
    with StateDB(db_path=db_path) as db:
        indexes = {
            r[0]
            for r in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_findings_created_at" in indexes
        assert "idx_findings_connection" in indexes
        assert "idx_dbt_findings_created_at" in indexes
