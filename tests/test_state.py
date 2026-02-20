from olly.config import ConnectionConfig, NamedConnection, OllyConfig, Selection
from olly.models import ColumnInfo, CostRecord, TableInfo, VolumeRecord
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
        assert "cost_snapshot" in tables


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
        assert "idx_cost_snapshot_sid" in indexes


def test_get_latest_cost(state_db):
    """get_latest_cost returns cost records from the most recent snapshot."""
    record = CostRecord(
        schema_name="main",
        table_name="orders",
        user_email="user@example.com",
        total_bytes_billed=1_000_000,
        estimated_cost_usd=5.0,
        query_count=3,
    )
    sid = state_db.create_snapshot()
    state_db.store_cost_data(sid, [record])

    latest = state_db.get_latest_cost()
    assert len(latest) == 1
    assert latest[0].estimated_cost_usd == 5.0
    assert latest[0].table_name == "orders"


def test_get_latest_cost_empty(state_db):
    """get_latest_cost returns empty list when no snapshots exist."""
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
