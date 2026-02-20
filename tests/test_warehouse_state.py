import ibis
import pytest

from olly.models import ColumnInfo, CostRecord, TableInfo, VolumeRecord
from olly.warehouse_state import WarehouseStateStore


@pytest.fixture
def wss():
    conn = ibis.duckdb.connect(":memory:")
    store = WarehouseStateStore(conn, "_olly_test", "duckdb")
    yield store


def test_create_snapshot(wss):
    sid = wss.create_snapshot()
    assert sid == 1
    sid2 = wss.create_snapshot()
    assert sid2 == 2


def test_create_snapshot_with_connection_name(wss):
    sid = wss.create_snapshot(connection_name="prod")
    assert sid == 1
    sid2 = wss.create_snapshot(connection_name="staging")
    assert sid2 == 2


def test_store_and_get_schema(wss):
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
    sid = wss.create_snapshot()
    wss.store_schema_data(sid, tables)

    schema = wss.get_latest_schema()
    assert len(schema) == 1
    assert schema[0].table_name == "orders"
    assert len(schema[0].columns) == 2


def test_store_and_get_volume(wss):
    volumes = [VolumeRecord("main", "orders", 100)]
    sid = wss.create_snapshot()
    wss.store_volume_data(sid, volumes)

    vols = wss.get_latest_volume()
    assert len(vols) == 1
    assert vols[0].row_count == 100


def test_volume_history(wss):
    counts = [100, 105, 102, 98, 110]
    for count in counts:
        sid = wss.create_snapshot()
        wss.store_volume_data(sid, [VolumeRecord("main", "orders", count)])

    history = wss.get_volume_history("main", "orders", 10)
    assert history == list(reversed(counts))


def test_prune_old_snapshots(wss):
    for i in range(10):
        sid = wss.create_snapshot()
        wss.store_volume_data(sid, [VolumeRecord("main", "t", i)])

    wss.prune_old_snapshots(keep=3)

    history = wss.get_volume_history("main", "t", 100)
    assert len(history) == 3
    assert history == [9, 8, 7]


def test_has_snapshots_empty(wss):
    assert not wss.has_snapshots()


def test_has_snapshots_after_insert(wss):
    wss.create_snapshot()
    assert wss.has_snapshots()


def test_unchanged_count(wss):
    for _ in range(5):
        sid = wss.create_snapshot()
        wss.store_volume_data(sid, [VolumeRecord("main", "t", 100)])

    assert wss.get_recent_volume_unchanged_count("main", "t", 10) == 5


def test_unchanged_count_with_change(wss):
    for count in [100, 100, 100, 200]:
        sid = wss.create_snapshot()
        wss.store_volume_data(sid, [VolumeRecord("main", "t", count)])

    assert wss.get_recent_volume_unchanged_count("main", "t", 10) == 1


def test_volume_timeseries(wss):
    for count in [10, 20, 30]:
        sid = wss.create_snapshot()
        wss.store_volume_data(sid, [VolumeRecord("main", "t", count)])

    ts = wss.get_volume_timeseries("main", "t")
    assert len(ts) == 3
    assert ts[0][1] == 10  # oldest first
    assert ts[2][1] == 30


def test_table_first_seen(wss):
    sid = wss.create_snapshot()
    wss.store_schema_data(
        sid, [TableInfo("main", "t", "TABLE", [ColumnInfo("id", "int", False)])]
    )

    first_seen, count = wss.get_table_first_seen("main", "t")
    assert first_seen is not None
    assert count == 1


def test_table_first_seen_missing(wss):
    first_seen, count = wss.get_table_first_seen("main", "nope")
    assert first_seen is None
    assert count == 0


def test_snapshot_ids_for_table(wss):
    for _ in range(3):
        sid = wss.create_snapshot()
        wss.store_schema_data(
            sid, [TableInfo("main", "t", "TABLE", [ColumnInfo("id", "int", False)])]
        )

    ids = wss.get_recent_snapshot_ids_for_table("main", "t", limit=2)
    assert len(ids) == 2
    assert ids[0] > ids[1]  # newest first


def test_columns_for_snapshot(wss):
    sid = wss.create_snapshot()
    wss.store_schema_data(
        sid,
        [
            TableInfo(
                "main",
                "t",
                "TABLE",
                [
                    ColumnInfo("id", "int", False),
                    ColumnInfo("name", "varchar", True),
                ],
            )
        ],
    )

    cols = wss.get_columns_for_snapshot(sid, "main", "t")
    assert cols["id"] == ("int", False)
    assert cols["name"] == ("varchar", True)


def test_cost_data(wss):
    record = CostRecord(
        schema_name="main",
        table_name="orders",
        user_email="user@example.com",
        total_bytes_billed=1_000_000,
        estimated_cost_usd=5.0,
        query_count=3,
    )
    sid = wss.create_snapshot()
    wss.store_cost_data(sid, [record])

    latest = wss.get_latest_cost()
    assert len(latest) == 1
    assert latest[0].estimated_cost_usd == 5.0


def test_cost_history(wss):
    for cost in [1.0, 2.0, 3.0]:
        sid = wss.create_snapshot()
        wss.store_cost_data(sid, [CostRecord("main", "t", "u@e.com", 100, cost, 1)])

    history = wss.get_cost_history(depth=10)
    assert len(history) == 3
    assert history[0][1] == 3.0  # newest first


def test_context_manager(wss):
    with wss as store:
        store.create_snapshot()
        assert store.has_snapshots()


def test_close_is_noop(wss):
    wss.close()
    # Should still work after close since it doesn't own the connection
    wss.create_snapshot()
    assert wss.has_snapshots()


def test_special_characters(wss):
    """Strings with quotes should be handled correctly."""
    tables = [
        TableInfo(
            schema_name="main",
            table_name="it's_a_table",
            table_type="TABLE",
            columns=[ColumnInfo("col'1", "varchar", True)],
        )
    ]
    sid = wss.create_snapshot()
    wss.store_schema_data(sid, tables)

    schema = wss.get_latest_schema()
    assert len(schema) == 1
    assert schema[0].table_name == "it's_a_table"
    assert schema[0].columns[0].column_name == "col'1"


def test_idempotent_schema_creation():
    """Creating WarehouseStateStore twice on same schema doesn't error."""
    conn = ibis.duckdb.connect(":memory:")
    WarehouseStateStore(conn, "_olly_test", "duckdb")
    WarehouseStateStore(conn, "_olly_test", "duckdb")


def test_empty_store_methods(wss):
    """Empty store returns sensible defaults for all query methods."""
    assert wss.get_latest_schema() == []
    assert wss.get_latest_volume() == []
    assert wss.get_latest_cost() == []
    assert wss.get_volume_history("main", "t", 10) == []
    assert wss.get_recent_volume_unchanged_count("main", "t", 10) == 0
    assert wss.get_cost_history(10) == []
    assert wss.get_volume_timeseries("main", "t") == []
    assert wss.get_recent_snapshot_ids_for_table("main", "t") == []
    assert wss.get_columns_for_snapshot(1, "main", "t") == {}


def test_store_empty_lists(wss):
    """Storing empty lists should not error."""
    sid = wss.create_snapshot()
    wss.store_schema_data(sid, [])
    wss.store_volume_data(sid, [])
    wss.store_cost_data(sid, [])
    assert wss.has_snapshots()


# --- Multi-connection isolation tests ---


def test_connection_name_isolates_snapshots(wss):
    """Snapshots for different connections are isolated."""
    wss.create_snapshot(connection_name="prod")
    wss.create_snapshot(connection_name="staging")

    assert wss.has_snapshots(connection_name="prod")
    assert wss.has_snapshots(connection_name="staging")
    assert not wss.has_snapshots(connection_name="dev")
    # Default empty string has no snapshots
    assert not wss.has_snapshots()


def test_connection_name_isolates_schema(wss):
    """Schema data is isolated by connection_name."""
    prod_tables = [
        TableInfo("main", "orders", "TABLE", [ColumnInfo("id", "int", False)]),
    ]
    staging_tables = [
        TableInfo("main", "users", "TABLE", [ColumnInfo("name", "varchar", True)]),
    ]

    sid_prod = wss.create_snapshot(connection_name="prod")
    wss.store_schema_data(sid_prod, prod_tables)

    sid_staging = wss.create_snapshot(connection_name="staging")
    wss.store_schema_data(sid_staging, staging_tables)

    prod_schema = wss.get_latest_schema(connection_name="prod")
    assert len(prod_schema) == 1
    assert prod_schema[0].table_name == "orders"

    staging_schema = wss.get_latest_schema(connection_name="staging")
    assert len(staging_schema) == 1
    assert staging_schema[0].table_name == "users"

    # Default connection has no schema
    assert wss.get_latest_schema() == []


def test_connection_name_isolates_volume(wss):
    """Volume data is isolated by connection_name."""
    sid_prod = wss.create_snapshot(connection_name="prod")
    wss.store_volume_data(sid_prod, [VolumeRecord("main", "orders", 1000)])

    sid_staging = wss.create_snapshot(connection_name="staging")
    wss.store_volume_data(sid_staging, [VolumeRecord("main", "orders", 50)])

    prod_vol = wss.get_latest_volume(connection_name="prod")
    assert len(prod_vol) == 1
    assert prod_vol[0].row_count == 1000

    staging_vol = wss.get_latest_volume(connection_name="staging")
    assert len(staging_vol) == 1
    assert staging_vol[0].row_count == 50

    assert wss.get_latest_volume() == []


def test_connection_name_isolates_volume_history(wss):
    """Volume history is scoped to connection_name."""
    for count in [100, 200, 300]:
        sid = wss.create_snapshot(connection_name="prod")
        wss.store_volume_data(sid, [VolumeRecord("main", "t", count)])

    for count in [10, 20]:
        sid = wss.create_snapshot(connection_name="staging")
        wss.store_volume_data(sid, [VolumeRecord("main", "t", count)])

    prod_history = wss.get_volume_history("main", "t", 10, connection_name="prod")
    assert prod_history == [300, 200, 100]

    staging_history = wss.get_volume_history("main", "t", 10, connection_name="staging")
    assert staging_history == [20, 10]

    assert wss.get_volume_history("main", "t", 10) == []


def test_connection_name_isolates_cost(wss):
    """Cost data is isolated by connection_name."""
    sid_prod = wss.create_snapshot(connection_name="prod")
    wss.store_cost_data(
        sid_prod, [CostRecord("main", "t", "u@e.com", 100, 50.0, 1)]
    )

    sid_staging = wss.create_snapshot(connection_name="staging")
    wss.store_cost_data(
        sid_staging, [CostRecord("main", "t", "u@e.com", 10, 1.0, 1)]
    )

    prod_cost = wss.get_latest_cost(connection_name="prod")
    assert len(prod_cost) == 1
    assert prod_cost[0].estimated_cost_usd == 50.0

    staging_cost = wss.get_latest_cost(connection_name="staging")
    assert len(staging_cost) == 1
    assert staging_cost[0].estimated_cost_usd == 1.0

    assert wss.get_latest_cost() == []


def test_connection_name_isolates_cost_history(wss):
    """Cost history is scoped to connection_name."""
    for cost in [1.0, 2.0]:
        sid = wss.create_snapshot(connection_name="prod")
        wss.store_cost_data(sid, [CostRecord("main", "t", "u@e.com", 100, cost, 1)])

    sid = wss.create_snapshot(connection_name="staging")
    wss.store_cost_data(sid, [CostRecord("main", "t", "u@e.com", 10, 99.0, 1)])

    prod_history = wss.get_cost_history(depth=10, connection_name="prod")
    assert len(prod_history) == 2
    assert prod_history[0][1] == 2.0

    staging_history = wss.get_cost_history(depth=10, connection_name="staging")
    assert len(staging_history) == 1
    assert staging_history[0][1] == 99.0


def test_connection_name_isolates_prune(wss):
    """Pruning only affects snapshots for the given connection_name."""
    for i in range(5):
        sid = wss.create_snapshot(connection_name="prod")
        wss.store_volume_data(sid, [VolumeRecord("main", "t", i)])

    for i in range(3):
        sid = wss.create_snapshot(connection_name="staging")
        wss.store_volume_data(sid, [VolumeRecord("main", "t", i + 100)])

    wss.prune_old_snapshots(keep=2, connection_name="prod")

    prod_history = wss.get_volume_history("main", "t", 100, connection_name="prod")
    assert len(prod_history) == 2
    assert prod_history == [4, 3]

    # Staging is untouched
    staging_history = wss.get_volume_history(
        "main", "t", 100, connection_name="staging"
    )
    assert len(staging_history) == 3


def test_connection_name_isolates_timeseries(wss):
    """Volume timeseries is scoped to connection_name."""
    for count in [10, 20]:
        sid = wss.create_snapshot(connection_name="prod")
        wss.store_volume_data(sid, [VolumeRecord("main", "t", count)])

    sid = wss.create_snapshot(connection_name="staging")
    wss.store_volume_data(sid, [VolumeRecord("main", "t", 99)])

    prod_ts = wss.get_volume_timeseries("main", "t", connection_name="prod")
    assert len(prod_ts) == 2
    assert prod_ts[0][1] == 10
    assert prod_ts[1][1] == 20

    staging_ts = wss.get_volume_timeseries("main", "t", connection_name="staging")
    assert len(staging_ts) == 1
    assert staging_ts[0][1] == 99


def test_connection_name_isolates_table_first_seen(wss):
    """Table first_seen is scoped to connection_name."""
    sid_prod = wss.create_snapshot(connection_name="prod")
    wss.store_schema_data(
        sid_prod, [TableInfo("main", "t", "TABLE", [ColumnInfo("id", "int", False)])]
    )

    first_seen, count = wss.get_table_first_seen("main", "t", connection_name="prod")
    assert first_seen is not None
    assert count == 1

    first_seen, count = wss.get_table_first_seen(
        "main", "t", connection_name="staging"
    )
    assert first_seen is None
    assert count == 0


def test_connection_name_isolates_snapshot_ids(wss):
    """Recent snapshot IDs for a table are scoped to connection_name."""
    for _ in range(3):
        sid = wss.create_snapshot(connection_name="prod")
        wss.store_schema_data(
            sid, [TableInfo("main", "t", "TABLE", [ColumnInfo("id", "int", False)])]
        )

    sid = wss.create_snapshot(connection_name="staging")
    wss.store_schema_data(
        sid, [TableInfo("main", "t", "TABLE", [ColumnInfo("id", "int", False)])]
    )

    prod_ids = wss.get_recent_snapshot_ids_for_table(
        "main", "t", limit=5, connection_name="prod"
    )
    assert len(prod_ids) == 3

    staging_ids = wss.get_recent_snapshot_ids_for_table(
        "main", "t", limit=5, connection_name="staging"
    )
    assert len(staging_ids) == 1


def test_connection_name_isolates_unchanged_count(wss):
    """Unchanged count is scoped to connection_name."""
    for _ in range(4):
        sid = wss.create_snapshot(connection_name="prod")
        wss.store_volume_data(sid, [VolumeRecord("main", "t", 100)])

    # Staging has a different value
    for _ in range(2):
        sid = wss.create_snapshot(connection_name="staging")
        wss.store_volume_data(sid, [VolumeRecord("main", "t", 200)])

    assert (
        wss.get_recent_volume_unchanged_count("main", "t", 10, connection_name="prod")
        == 4
    )
    assert (
        wss.get_recent_volume_unchanged_count(
            "main", "t", 10, connection_name="staging"
        )
        == 2
    )
